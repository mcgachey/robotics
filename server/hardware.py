"""Droids on the Pi: list the ESP32 boards, assign a student's built code to one, run it (Deploy) and stop it.

A deploy runs the student's built jar in its own limited JVM through robotics.DeployRunner, which drives the
droid via the board controller's HTTP API (loopback only). Each droid has zero or one assignment, which is
remembered across restarts; the run itself is a Job so its output streams like a build's.
"""
import json
import logging
import re
import threading
import urllib.error
import urllib.request

from .builder import _env
from .jobs import JobBusy
from .procs import run_limited
from .storage import lock_for, read_json, write_json

log = logging.getLogger("robotics.hardware")

BOARD_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class HardwareError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Controller:
    """The board controller's HTTP API (astromech_server raspberrypi_controller)."""

    def __init__(self, base_url: str, timeout: float = 4.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data is not None else {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("message") or e.reason
            except (ValueError, AttributeError):
                msg = e.reason
            raise HardwareError(f"The board controller said: {msg}", 502) from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise HardwareError(f"Cannot reach the board controller at {self.base} ({e}).", 503) from e

    def droids(self) -> list[dict]:
        """Droid boards the controller knows, online ones first."""
        boards = self._call("GET", "/api/boards") or []
        out = [{"id": b["device_id"], "name": b.get("name") or b["device_id"], "online": bool(b.get("online")),
                "port": b.get("port", ""), "firmware": (b.get("info") or {}).get("firmware_version", "")}
               for b in boards if b.get("role") == "droid"]
        out.sort(key=lambda d: (not d["online"], d["name"].lower()))
        return out

    def stop(self, board_id: str) -> None:
        self._call("POST", f"/api/boards/{board_id}/commands/stop", {})


class Hardware:
    def __init__(self, cfg, projects, lessons, accounts, jobs, service, controller: Controller | None = None):
        self.cfg = cfg
        self.projects = projects
        self.lessons = lessons
        self.accounts = accounts
        self.jobs = jobs
        self.service = service
        self.controller = controller or Controller(cfg.controller_url)
        self.path = cfg.data_dir / "hardware.json"

    # --- assignments -------------------------------------------------------
    def _assignments(self) -> dict:
        return read_json(self.path) or {}

    @staticmethod
    def _owner(board_id: str) -> str:
        return f"droid-{board_id}"

    def _active(self, board_id: str):
        return self.jobs.active_for(self._owner(board_id))

    # --- views -------------------------------------------------------------
    def overview(self) -> dict:
        try:
            boards, error = self.controller.droids(), ""
        except HardwareError as e:
            boards, error = [], str(e)
        assigned = self._assignments()
        titles = {m["id"]: m["title"] for m in self.lessons.list_with_state()}
        names = {s["id"]: s["name"] for s in self.accounts.students()}
        droids = []
        for b in boards:
            a = assigned.get(b["id"])
            job = self._active(b["id"])
            droids.append({**b,
                           "assignment": a and {**a, "studentName": names.get(a["studentId"], "?"),
                                                "lessonTitle": titles.get(a["lessonId"], a["lessonId"])},
                           "run": job and {"jobId": job.id, "startedAt": job.started_at}})
        students = []
        for s in self.accounts.students():
            builds = [{**d, "lessonTitle": titles.get(d["lessonId"], d["lessonId"])}
                      for d in self.projects.deployable(s["id"])]
            if builds:
                students.append({"id": s["id"], "name": s["name"], "login": s.get("login", ""), "builds": builds})
        return {"controller": {"ok": not error, "url": self.cfg.controller_url, "error": error},
                "droids": droids, "students": students}

    # --- deploy / stop -----------------------------------------------------
    def deploy(self, board_id: str, sid: str, lid: str, rev: object) -> object:
        """Start the student's built revision on the droid. Returns the Job. Raises HardwareError / JobBusy."""
        if not isinstance(board_id, str) or not BOARD_ID.match(board_id):
            raise HardwareError("No such droid.", 404)
        if not isinstance(rev, int) or isinstance(rev, bool):
            raise HardwareError("Choose a revision.")
        student, meta = self.accounts.student(sid), self.lessons.meta(lid)
        if not student or not meta:
            raise HardwareError("No such student or lesson.", 404)
        build = self.projects.good_build(sid, lid, rev) if self.projects.exists(sid, lid) else None
        if not build:
            raise HardwareError("That revision has not been built. Build it first.", 409)
        build_id, jar = build
        droid = next((d for d in self.controller.droids() if d["id"] == board_id), None)
        if droid is None:
            raise HardwareError("The board controller does not know that droid.", 404)
        if not droid["online"]:
            raise HardwareError(f"{droid['name']} is offline. Check its USB cable, then rescan on the controller.", 409)

        def run(job):
            self._run(job, board_id, jar, meta["className"])

        with lock_for(f"hardware:{board_id}"):
            try:
                job = self.jobs.start(kind="deploy", origin="instructor-deploy", owner=self._owner(board_id),
                                      student_id=sid, lesson_id=lid, revision=rev, class_name=meta["className"],
                                      api_version=meta.get("apiVersion", 0), run=run, board_id=board_id)
            except JobBusy as e:
                raise HardwareError(str(e), 409) from e
            assigned = self._assignments()
            assigned[board_id] = {"studentId": sid, "lessonId": lid, "revision": rev, "buildId": build_id,
                                  "jobId": job.id, "assignedAt": job.started_at}
            write_json(self.path, assigned)
        return job

    def stop(self, board_id: str) -> None:
        """Stop the running program, if any, and make sure the droid's wheels are stopped."""
        if not isinstance(board_id, str) or not BOARD_ID.match(board_id):
            raise HardwareError("No such droid.", 404)
        job = self._active(board_id)
        if job:
            job.cancel.set()
        else:
            self.controller.stop(board_id)

    def unassign(self, board_id: str) -> None:
        if not isinstance(board_id, str) or not BOARD_ID.match(board_id):
            raise HardwareError("No such droid.", 404)
        if self._active(board_id):
            raise HardwareError("This droid is running a program. Stop it first.", 409)
        with lock_for(f"hardware:{board_id}"):
            assigned = self._assignments()
            if assigned.pop(board_id, None) is not None:
                write_json(self.path, assigned)

    # --- the run -----------------------------------------------------------
    def _run(self, job, board_id: str, jar, class_name: str) -> None:
        cfg = self.cfg
        job.emit("status", f"Running {class_name} (revision {job.revision}) on the droid, "
                           f"for at most {cfg.deploy_max_sec} seconds")
        cmd = [cfg.java] + self.service._jvm_flags() + [
            "-XX:+ExitOnOutOfMemoryError", "-Djava.awt.headless=true", "-cp", f"{jar}:{cfg.api_jar}",
            "robotics.DeployRunner", class_name, board_id, cfg.controller_url]
        try:
            r = run_limited(cmd, job.dir, cfg.deploy_max_sec, cfg.max_output_kb * 1024, cancel=job.cancel,
                            on_output=lambda t: job.emit("output", t), env=_env(job.dir))
        finally:
            # The runner stops the motors itself on a normal exit, but not when it is killed (Stop, time
            # limit, output limit), so always send a stop as well.
            self._stop_droid(job, board_id)
        job.durations["runMs"] = r.elapsed_ms
        job.program_output = r.output
        if r.cancelled:
            job.set_result("cancelled", "cancelled", "Stopped.")
        elif r.timed_out:
            job.set_result("cancelled", "time_limit", f"Stopped automatically after {cfg.deploy_max_sec} seconds.")
        elif r.output_exceeded:
            job.set_result("failed", "output_limit", "The program printed too much text and was stopped.")
        elif r.returncode == 0:
            job.set_result("passed", "", "The program finished.")
        else:
            job.set_result("failed", "run_error", "The program stopped with an error. See the output.")
        job.emit("status", job.message)

    def _stop_droid(self, job, board_id: str) -> None:
        try:
            self.controller.stop(board_id)
        except HardwareError as e:
            job.emit("status", f"WARNING: could not confirm that the droid stopped ({e}). "
                               "If it is still moving, switch it off.")
