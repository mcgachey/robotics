"""Plan step 3: the build service against good source, a compile error, a failing test,
an infinite loop and runaway output."""
import subprocess
import time
from pathlib import Path

import pytest

from server.builder import BuildService
from server.jobs import Job
from server.tests.conftest import EXIT, FLOOD, GOOD, INFINITE, LESSON0, STARTER, SYNTAX_ERROR


@pytest.fixture
def run(app, tmp_path):
    rt = app.robotics

    def _run(source: str, kind="test"):
        src = tmp_path / "in" / "HelloWorld.java"
        src.parent.mkdir(exist_ok=True)
        src.write_text(source)
        lesson = rt.lessons.meta("lesson0")
        job = Job(f"j{time.time_ns()}", kind, "student", "o", "s", "lesson0", 1, tmp_path / f"job{time.time_ns()}",
                  class_name="HelloWorld")
        rt.service.execute(job, src, lesson)
        return job
    return _run


@pytest.fixture
def lesson(app, instructor, lesson0):
    return app.robotics.lessons.meta("lesson0")


def test_good_source_passes(run, lesson):
    j = run(GOOD)
    assert j.status == "passed", (j.message, j.output)
    assert [t["status"] for t in j.tests] == ["passed"]
    assert (j.dir / "artifact.jar").exists() and j.compiled


def test_build_only_does_not_run_tests(run, lesson):
    j = run(GOOD, kind="build")
    assert j.status == "passed" and j.tests == [] and j.message.startswith("Build succeeded")


def test_compile_error_has_structured_diagnostic(run, lesson):
    j = run(SYNTAX_ERROR)
    assert j.status == "failed" and j.reason == "compile_error"
    assert not (j.dir / "artifact.jar").exists()
    (d,) = j.diagnostics
    assert d["line"] == 6 and d["severity"] == "error" and "semicolon" in d["message"].lower()


def test_failing_test_is_readable(run, lesson):
    j = run(STARTER)
    assert j.status == "failed" and j.reason == "test_failure"
    assert j.tests[0]["status"] == "failed"
    assert 'Hello, world!' in j.tests[0]["message"]


def test_student_stdout_is_captured_as_program_output(run, lesson):
    j = run(GOOD.replace('robot.log("Hello, world!");', 'robot.log("Hello, world!"); System.out.println("from student");'))
    assert j.status == "passed" and "from student" in j.program_output


def test_infinite_loop_is_killed_at_timeout(run, lesson):
    t0 = time.time()
    j = run(INFINITE)
    assert j.status == "failed" and j.reason == "timeout" and "ran too long" in j.message
    assert time.time() - t0 < 15
    assert subprocess.run(["pgrep", "-f", str(j.dir)], capture_output=True).returncode != 0  # no orphan JVM


def test_runaway_output_is_capped_and_killed(run, lesson):
    j = run(FLOOD)
    assert j.status == "failed" and j.reason == "output_limit"
    assert len(j.output) < 100_000
    assert subprocess.run(["pgrep", "-f", str(j.dir)], capture_output=True).returncode != 0


def test_system_exit_is_reported_not_a_server_error(run, lesson):
    j = run(EXIT)
    assert j.status == "failed" and j.reason == "crashed"


def test_cancel_kills_the_tree(app, lesson, tmp_path):
    import threading
    rt = app.robotics
    src = tmp_path / "HelloWorld.java"
    src.write_text(INFINITE)
    job = Job("jc", "test", "student", "o", "s", "lesson0", 1, tmp_path / "jc", class_name="HelloWorld")
    t = threading.Thread(target=rt.service.execute, args=(job, src, lesson))
    t.start()
    end = time.time() + 30
    while "Running the tests" not in job.output and t.is_alive() and time.time() < end:
        time.sleep(0.05)
    job.cancel.set()
    t.join(10)
    assert not t.is_alive() and job.status == "cancelled"
    assert subprocess.run(["pgrep", "-f", str(job.dir)], capture_output=True).returncode != 0


def test_robot_log_messages_are_captured_separately_from_stdout(run, lesson):
    j = run(GOOD.replace('robot.log("Hello, world!");', 'robot.log("Hello, world!"); System.out.println("from student");'))
    assert j.robot_log == "Hello, world!\n"
    assert "Hello, world!" not in j.program_output


def test_lesson_timeout_overrides_server_default(app, run, lesson, monkeypatch):
    real = app.robotics.lessons.meta
    monkeypatch.setattr(app.robotics.lessons, "meta", lambda lid: {**real(lid), "timeout": 2})
    t0 = time.time()
    j = run(INFINITE)
    assert j.reason == "timeout" and "more than 2 seconds" in j.message
    assert time.time() - t0 < 10 and app.robotics.cfg.timeout_sec > 2
