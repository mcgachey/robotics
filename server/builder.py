"""The build service: compile student code and run lesson tests, each in a limited child process (D6)."""
import hashlib
import json
import os
import shutil
import threading
import zipfile
from pathlib import Path

from .diagnostics import parse_javac
from .jobs import Job
from .procs import ProcResult, run_limited


def _env(home: Path) -> dict:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), "LC_ALL": "C.UTF-8"}
    if "JAVA_HOME" in os.environ:
        env["JAVA_HOME"] = os.environ["JAVA_HOME"]
    return env


class BuildService:
    def __init__(self, cfg, lessons):
        self.cfg = cfg
        self.lessons = lessons

    # --- entry point -----------------------------------------------------
    def execute(self, job: Job, source_file: Path, lesson: dict, reuse: tuple[str, Path] | None = None) -> None:
        """Build (kind=build) or build-if-needed-then-test (kind=test) one immutable source file.

        reuse = (build id, artifact.jar) of an existing successful build of this exact revision.
        """
        job.dir.mkdir(parents=True, exist_ok=True)
        if reuse:
            job.artifact_build_id, jar = reuse
            job.emit("status", f"Using the successful build of revision {job.revision}")
        else:
            jar = self._compile(job, source_file, lesson)
            if jar is None:
                return
            job.artifact_build_id, job.compiled = job.id, True
        if job.cancel.is_set():
            return self._cancelled(job)
        if job.kind == "build":
            warn = sum(1 for d in job.diagnostics if d["severity"] == "warning")
            job.set_result("passed", "", "Build succeeded" + (f" with {warn} warning(s)." if warn else "."))
            job.emit("status", job.message)
            return
        self._test(job, lesson, jar)

    # --- helpers ---------------------------------------------------------
    def _limits(self) -> tuple[int, int]:
        return self.cfg.timeout_sec, self.cfg.max_output_kb * 1024

    def _jvm_flags(self) -> list[str]:
        return [f"-Xmx{self.cfg.max_heap_mb}m", "-XX:+UseSerialGC", "-XX:TieredStopAtLevel=1", "-Xshare:auto",
                "-XX:-UsePerfData"]  # no hsperfdata mmap file: faster JVM start, nothing to clean up

    def _javac(self, job: Job, args: list[str]) -> ProcResult:
        timeout, cap = self._limits()
        cmd = [self.cfg.javac] + [f"-J{f}" for f in self._jvm_flags()] + [
            "--release", "8", "-Xlint:-options", "-encoding", "UTF-8", "-proc:none"] + args
        return run_limited(cmd, job.dir, timeout, cap, cancel=job.cancel,
                           on_output=lambda t: job.emit("output", t), env=_env(job.dir))

    def _cancelled(self, job: Job) -> None:
        job.set_result("cancelled", "cancelled", "Stopped.")
        job.emit("status", job.message)

    def _killed(self, job: Job, r: ProcResult, what: str) -> bool:
        """Turn a killed child into a friendly result. True if it was killed."""
        if r.cancelled:
            self._cancelled(job)
        elif r.timed_out:
            job.set_result("failed", "timeout", f"Your program ran too long (more than {self.cfg.timeout_sec} seconds) "
                           f"and was stopped. Is there a loop that never ends?" if what == "tests" else
                           f"The compiler ran too long (more than {self.cfg.timeout_sec} seconds) and was stopped.")
        elif r.output_exceeded:
            job.set_result("failed", "output_limit", "Your program printed too much text and was stopped. "
                           "Is something printing inside a loop that never ends?")
        else:
            return False
        if not r.cancelled:
            job.emit("status", job.message)
        return True

    # --- compile ---------------------------------------------------------
    def _compile(self, job: Job, source_file: Path, lesson: dict) -> Path | None:
        cls = lesson["className"]
        src_dir, classes = job.dir / "src", job.dir / "classes"
        shutil.rmtree(classes, ignore_errors=True)
        src_dir.mkdir(exist_ok=True)
        classes.mkdir()
        src = src_dir / f"{cls}.java"
        shutil.copyfile(source_file, src)
        job.emit("status", f"Compiling {cls}.java (revision {job.revision})")
        r = self._javac(job, ["-cp", str(self.cfg.api_jar), "-d", str(classes), str(src)])
        job.durations["compileMs"] = r.elapsed_ms
        if self._killed(job, r, "compile"):
            return None
        job.diagnostics = parse_javac(r.output)
        if r.returncode != 0:
            errors = [d for d in job.diagnostics if d["severity"] == "error"]
            if errors:
                first = errors[0]
                more = f" (and {len(errors) - 1} more)" if len(errors) > 1 else ""
                job.set_result("failed", "compile_error",
                               f"Build failed: line {first['line']}: {first['message']}{more}")
            else:
                job.set_result("failed", "compile_error", "Build failed. See the raw output for details.")
            job.emit("status", job.message)
            return None
        jar = job.dir / "artifact.jar"
        tmp = job.dir / "artifact.jar.tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(classes.rglob("*.class")):
                z.write(p, p.relative_to(classes).as_posix())
        os.replace(tmp, jar)
        os.chmod(jar, 0o444)
        job.emit("status", "Compiled successfully")
        return jar

    # --- test ------------------------------------------------------------
    def _tests_key(self, files: list[Path]) -> str:
        h = hashlib.sha256()
        for f in files:
            h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
        for p in (self.cfg.api_jar, self.cfg.junit_jar, self.cfg.hamcrest_jar):
            try:
                st = p.stat()
                h.update(f"{p}:{st.st_size}:{st.st_mtime_ns}".encode())
            except OSError:
                pass
        return h.hexdigest()[:32]

    @staticmethod
    def _publish_tests(built: Path, cached: Path) -> None:
        """Best-effort atomic copy of freshly compiled test classes into the shared cache."""
        tmp = cached.with_name(f"{cached.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            cached.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(built, tmp)
            os.rename(tmp, cached)  # loses harmlessly to a concurrent publisher
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)

    def _test(self, job: Job, lesson: dict, jar: Path) -> None:
        tests_src = job.dir / "tests"
        shutil.rmtree(tests_src, ignore_errors=True)
        files = sorted(self.lessons.tests_dir(lesson).glob("*.java"))
        if not files:
            job.set_result("failed", "lesson_error", "This lesson has no tests yet. Tell your teacher.")
            job.emit("status", job.message)
            return
        libs = os.pathsep.join([str(jar), self.cfg.classpath_libs])

        # The lesson's tests only depend on the lesson's test sources and the API/JUnit jars (they are
        # compiled against the student's classes only by name at run time), so compile them once and
        # reuse the result for every student and job instead of paying for a second javac JVM each time.
        key = self._tests_key(files)
        cached = self.cfg.data_dir / "cache" / "testclasses" / key
        tests_out = cached
        if cached.is_dir():
            job.emit("status", "Using the lesson's compiled tests")
        else:
            tests_src.mkdir()
            for f in files:
                shutil.copyfile(f, tests_src / f.name)
            tests_out = job.dir / "testclasses"
            shutil.rmtree(tests_out, ignore_errors=True)
            tests_out.mkdir()
            job.emit("status", "Compiling the lesson's tests")
            r = self._javac(job, ["-cp", libs, "-d", str(tests_out)] + [str(tests_src / f.name) for f in files])
            job.durations["testCompileMs"] = r.elapsed_ms
            if self._killed(job, r, "compile"):
                return
            if r.returncode != 0:
                job.set_result("failed", "lesson_error",
                               "The lesson's tests did not compile, so this is not your mistake. Tell your teacher.")
                job.emit("status", job.message)
                return
            self._publish_tests(tests_out, cached)
            if cached.is_dir():
                tests_out = cached

        job.emit("status", "Running the tests")
        results = job.dir / "results.json"
        results.unlink(missing_ok=True)
        timeout, cap = self._limits()
        cp = os.pathsep.join([str(tests_out), str(self.cfg.harness_jar), libs])
        cmd = [self.cfg.java] + self._jvm_flags() + ["-XX:+ExitOnOutOfMemoryError", "-Djava.awt.headless=true",
               "-cp", cp, "robotics.harness.JUnitHarness", str(results), self.lessons.test_class(lesson)]
        r = run_limited(cmd, job.dir, timeout, cap, cancel=job.cancel,
                        on_output=lambda t: job.emit("output", t), env=_env(job.dir))
        job.durations["testMs"] = r.elapsed_ms
        job.program_output = r.output
        if self._killed(job, r, "tests"):
            return
        try:
            job.tests = json.loads(results.read_text("utf-8"))
        except (FileNotFoundError, ValueError):
            job.set_result("failed", "crashed", "Your program stopped the tests early. "
                           "Does it call System.exit(), or run out of memory?")
            job.emit("status", job.message)
            return
        total = len(job.tests)
        bad = [t for t in job.tests if t["status"] in ("failed", "error")]
        if total == 0:
            job.set_result("failed", "lesson_error", "The lesson's tests did not run any checks. Tell your teacher.")
        elif bad:
            job.set_result("failed", "test_failure", f"{len(bad)} of {total} test(s) failed.")
        else:
            job.set_result("passed", "", f"All {total} test(s) passed.")
        job.emit("status", job.message)
