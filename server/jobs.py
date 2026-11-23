"""Async jobs: one active job per owner, a small global limit, Stop, and streamed events."""
import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .storage import read_json, write_json, atomic_write_text

log = logging.getLogger("robotics.jobs")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobBusy(Exception):
    """The owner already has a job running."""


class ServerBusy(Exception):
    """The global concurrency limit is reached."""


class Job:
    def __init__(self, job_id: str, kind: str, origin: str, owner: str, student_id: str, lesson_id: str,
                 revision: int, directory: Path, class_name: str = "", api_version: int = 0,
                 output_cap: int = 262144):
        self.id = job_id
        self.kind = kind            # "build" | "test"
        self.origin = origin        # "student" | "instructor-verify"
        self.owner = owner          # student id, or "instructor"
        self.student_id = student_id
        self.lesson_id = lesson_id
        self.revision = revision
        self.dir = Path(directory)
        self.class_name = class_name
        self.api_version = api_version
        self.status = "running"     # running | passed | failed | cancelled
        self.reason = ""            # compile_error | test_failure | timeout | output_limit | cancelled | interrupted | ...
        self.message = ""
        self.artifact_build_id: str | None = None
        self.compiled = False       # this job produced an artifact
        self.diagnostics: list[dict] = []
        self.tests: list[dict] = []
        self.durations: dict[str, int] = {}
        self.started_at = now_iso()
        self.finished_at: str | None = None
        self.output = ""
        self.program_output = ""
        self.cancel = threading.Event()
        self.events: list[dict] = []
        self.finished = False
        self.published = False      # result becomes visible only once fully recorded (see JobManager._run)
        self._output_cap = output_cap
        self._cond = threading.Condition()

    # --- events ----------------------------------------------------------
    def emit(self, type_: str, text: str = "", **extra) -> None:
        with self._cond:
            if type_ == "output":
                if len(self.output) < self._output_cap * 2:
                    self.output += text
            elif type_ == "status":
                self.output += f"== {text}\n"
            self.events.append({"id": len(self.events) + 1, "type": type_, "text": text, **extra})
            self._cond.notify_all()

    def wait_events(self, after: int, timeout: float) -> tuple[list[dict], bool]:
        """Events with id > after; blocks up to timeout for more. Returns (events, finished)."""
        with self._cond:
            if len(self.events) <= after and not self.finished:
                self._cond.wait(timeout)
            return self.events[after:], self.finished

    def mark_done(self) -> None:
        with self._cond:
            self.finished = True
            self.events.append({"id": len(self.events) + 1, "type": "done", "text": "", "job": self.to_dict()})
            self._cond.notify_all()

    # --- result ----------------------------------------------------------
    def set_result(self, status: str, reason: str, message: str) -> None:
        self.status, self.reason, self.message = status, reason, message

    def to_dict(self, include_output: bool = False) -> dict:
        d = {
            "id": self.id, "kind": self.kind, "origin": self.origin, "owner": self.owner,
            "studentId": self.student_id, "lessonId": self.lesson_id, "revision": self.revision,
            "className": self.class_name, "apiVersion": self.api_version,
            "status": self.status if self.published else "running",
            "reason": self.reason if self.published else "",
            "message": self.message if self.published else "",
            "artifactBuildId": self.artifact_build_id, "compiled": self.compiled,
            "hasArtifact": (self.dir / "artifact.jar").exists(),
            "startedAt": self.started_at, "finishedAt": self.finished_at,
            "durations": self.durations, "diagnostics": self.diagnostics, "tests": self.tests,
        }
        if include_output:
            d["output"] = self.output
            d["programOutput"] = self.program_output
        return d

    def save(self) -> None:
        write_json(self.dir / "build.json", self.to_dict())

    def save_output(self) -> None:
        atomic_write_text(self.dir / "output.log", self.output)
        if self.program_output:
            atomic_write_text(self.dir / "program-output.log", self.program_output)


def load_job_dict(builds_dir: Path, job_id: str, include_output: bool = True) -> dict | None:
    """A finished job's record from disk (survives restarts)."""
    d = Path(builds_dir) / job_id
    rec = read_json(d / "build.json")
    if rec is None:
        return None
    if include_output:
        for key, name in (("output", "output.log"), ("programOutput", "program-output.log")):
            try:
                rec[key] = (d / name).read_text("utf-8", "replace")
            except FileNotFoundError:
                rec[key] = ""
    return rec


class JobManager:
    KEEP_FINISHED = 100

    def __init__(self, cfg, service):
        self.cfg = cfg
        self.service = service
        self.builds_dir = Path(cfg.data_dir) / "builds"
        self.builds_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._active: dict[str, Job] = {}   # owner -> running job
        self._jobs: dict[str, Job] = {}     # recent jobs by id (running and finished)
        self.recover_interrupted()

    def recover_interrupted(self) -> int:
        """Jobs that were running at shutdown can never finish: mark them failed (interrupted)."""
        n = 0
        for d in self.builds_dir.iterdir() if self.builds_dir.exists() else []:
            rec = read_json(d / "build.json")
            if rec and rec.get("status") == "running":
                rec.update(status="failed", reason="interrupted", finishedAt=now_iso(),
                           message="The server restarted while this was running. Please try again.")
                write_json(d / "build.json", rec)
                n += 1
        return n

    def new_id(self) -> str:
        return f"{int(time.time())}-{secrets.token_hex(3)}"

    def active_for(self, owner: str) -> Job | None:
        with self._lock:
            return self._active.get(owner)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def start(self, *, kind: str, origin: str, owner: str, student_id: str, lesson_id: str, revision: int,
              class_name: str, api_version: int, run, on_finish=None) -> Job:
        """run(job) does the work (it should call service.execute). Raises JobBusy/ServerBusy."""
        with self._lock:
            if owner in self._active:
                raise JobBusy("You already have a build or test running. Wait for it to finish, or press Stop.")
            if len(self._active) >= self.cfg.max_concurrent_jobs:
                raise ServerBusy("The server is busy with other builds. Try again in a few seconds.")
            job_id = self.new_id()
            d = self.builds_dir / job_id
            d.mkdir(parents=True)
            job = Job(job_id, kind, origin, owner, student_id, lesson_id, revision, d,
                      class_name=class_name, api_version=api_version, output_cap=self.cfg.max_output_kb * 1024)
            self._active[owner] = job
            self._jobs[job_id] = job
            job.save()
            threading.Thread(target=self._run, args=(job, run, on_finish), daemon=True,
                             name=f"job-{job_id}").start()
        return job

    def _run(self, job: Job, run, on_finish) -> None:
        t0 = time.monotonic()
        try:
            run(job)
        except Exception as e:  # never let a worker thread die silently
            log.exception("job %s crashed", job.id)
            job.set_result("failed", "internal", f"Something went wrong inside the server ({type(e).__name__}). "
                                                 "Tell your instructor.")
        finally:
            if job.status == "running":
                job.set_result("failed", "internal", "The job ended without a result.")
            job.durations["totalMs"] = int((time.monotonic() - t0) * 1000)
            job.finished_at = now_iso()
            try:
                job.save_output()
                if on_finish:
                    on_finish(job)
            except Exception:
                log.exception("finishing job %s", job.id)
            with self._lock:
                if self._active.get(job.owner) is job:
                    del self._active[job.owner]
            job.published = True   # from here pollers see the result, the project is updated, the owner is free
            try:
                job.save()
            except Exception:
                log.exception("saving job %s", job.id)
            with self._lock:
                finished = [j for j in self._jobs.values() if j.finished]
                for old in finished[:max(0, len(finished) - self.KEEP_FINISHED)]:
                    self._jobs.pop(old.id, None)
            job.mark_done()
