"""Student workspaces, immutable revision snapshots, the Submit gate (D3) and the queue."""
import shutil
from pathlib import Path

from .jobs import now_iso
from .lessons import Lessons
from .storage import atomic_write_bytes, lock_for, read_json, valid_id, write_json


class ProjectError(ValueError):
    pass


class Projects:
    def __init__(self, data_dir: Path, lessons: Lessons, max_source_kb: int = 256):
        self.data_dir = Path(data_dir)
        self.lessons = lessons
        self.max_source = max_source_kb * 1024
        self.workspaces = self.data_dir / "workspaces"
        self.builds = self.data_dir / "builds"
        self.queue_dir = self.data_dir / "queue"

    # --- paths -----------------------------------------------------------
    def dir(self, sid: str, lid: str) -> Path:
        return self.workspaces / sid / lid

    def _lock(self, sid: str, lid: str):
        return lock_for(f"project:{sid}:{lid}")

    def source_path(self, sid: str, lid: str, cls: str) -> Path:
        return self.dir(sid, lid) / "src" / f"{cls}.java"

    def revision_path(self, sid: str, lid: str, cls: str, rev: int) -> Path:
        return self.dir(sid, lid) / "revisions" / str(rev) / f"{cls}.java"

    # --- open / save -----------------------------------------------------
    def open(self, sid: str, lid: str) -> dict:
        """The project record; created from the lesson's starter on first use (a copy, never a link)."""
        lesson = self.lessons.meta(lid)
        if not lesson:
            raise KeyError(lid)
        with self._lock(sid, lid):
            pj = read_json(self.dir(sid, lid) / "project.json")
            if pj is None:
                starter = self.lessons.starter_path(lesson)
                data = starter.read_bytes() if starter.exists() else b""
                atomic_write_bytes(self.source_path(sid, lid, lesson["className"]), data)
                pj = {"studentId": sid, "lessonId": lid, "className": lesson["className"], "revision": 0,
                      "lastBuild": None, "lastGoodBuild": None, "lastTest": None, "lastSubmit": None,
                      "goodBuilds": {}, "createdAt": now_iso()}
                write_json(self.dir(sid, lid) / "project.json", pj)
            return pj

    def exists(self, sid: str, lid: str) -> bool:
        return (self.dir(sid, lid) / "project.json").exists()

    def read_source(self, sid: str, lid: str) -> str:
        pj = self.open(sid, lid)
        return self.source_path(sid, lid, pj["className"]).read_text("utf-8", "replace")

    def save_source(self, sid: str, lid: str, text: object) -> None:
        if not isinstance(text, str):
            raise ProjectError("The source must be text.")
        data = text.encode("utf-8")
        if len(data) > self.max_source:
            raise ProjectError("The source file is too large.")
        pj = self.open(sid, lid)
        atomic_write_bytes(self.source_path(sid, lid, pj["className"]), data)

    # --- revisions -------------------------------------------------------
    def snapshot(self, sid: str, lid: str) -> tuple[int, Path]:
        """Snapshot the working copy as an immutable revision (reusing the latest if identical)."""
        with self._lock(sid, lid):
            pj = self.open(sid, lid)
            cls = pj["className"]
            cur = self.source_path(sid, lid, cls).read_bytes()
            n = pj["revision"]
            if n > 0:
                latest = self.revision_path(sid, lid, cls, n)
                if latest.exists() and latest.read_bytes() == cur:
                    return n, latest
            n += 1
            path = self.revision_path(sid, lid, cls, n)
            atomic_write_bytes(path, cur, mode=0o444)
            pj["revision"] = n
            write_json(self.dir(sid, lid) / "project.json", pj)
            return n, path

    def revisions(self, sid: str, lid: str) -> list[int]:
        d = self.dir(sid, lid) / "revisions"
        return sorted(int(p.name) for p in d.iterdir() if p.name.isdigit()) if d.is_dir() else []

    def good_build(self, sid: str, lid: str, rev: int) -> tuple[str, Path] | None:
        """(job id, artifact.jar) of a successful build of exactly this revision, if one still exists."""
        pj = self.open(sid, lid)
        bid = pj["goodBuilds"].get(str(rev))
        if bid and valid_id(bid):
            jar = self.builds / bid / "artifact.jar"
            if jar.exists():
                return bid, jar
        return None

    # --- results ---------------------------------------------------------
    def record_job(self, job) -> None:
        """Called when a student's own job finishes. Never touched by instructor-verify jobs."""
        sid, lid = job.student_id, job.lesson_id
        with self._lock(sid, lid):
            pj = self.open(sid, lid)
            ref = {"jobId": job.id, "revision": job.revision, "status": job.status, "reason": job.reason}
            if job.status in ("passed", "failed") and job.reason not in ("interrupted", "internal"):
                if job.kind == "build" or job.compiled or job.reason == "compile_error":
                    pj["lastBuild"] = {**ref, "status": "passed" if job.compiled else "failed"}
                if job.kind == "test":
                    pj["lastTest"] = ref
            if job.compiled:
                pj["lastGoodBuild"] = {"jobId": job.id, "revision": job.revision}
                pj["goodBuilds"][str(job.revision)] = job.id
            write_json(self.dir(sid, lid) / "project.json", pj)

    def state(self, sid: str, lid: str) -> dict:
        pj = self.open(sid, lid)
        return {
            "lessonId": lid, "className": pj["className"], "revision": pj["revision"],
            "lastBuild": pj["lastBuild"], "lastGoodBuild": pj["lastGoodBuild"],
            "lastTest": pj["lastTest"], "lastSubmit": pj["lastSubmit"],
            "canSubmit": self.can_submit(sid, lid),
        }

    def can_submit(self, sid: str, lid: str) -> bool:
        """D3: the latest Test passed, and it tested exactly the current working source."""
        pj = self.open(sid, lid)
        t = pj["lastTest"]
        if not t or t["status"] != "passed":
            return False
        rev = self.revision_path(sid, lid, pj["className"], t["revision"])
        src = self.source_path(sid, lid, pj["className"])
        try:
            return rev.read_bytes() == src.read_bytes()
        except FileNotFoundError:
            return False

    # --- submit and queue ------------------------------------------------
    def submit(self, sid: str, lid: str) -> dict:
        with self._lock(sid, lid):
            if not self.can_submit(sid, lid):
                raise ProjectError("Submit needs a passing Test of your current code. "
                                   "Press Test first, and Test again after any change.")
            pj = self.open(sid, lid)
            t = pj["lastTest"]
            entry = {"studentId": sid, "lessonId": lid, "buildId": t["jobId"], "revision": t["revision"],
                     "submittedAt": now_iso()}
            write_json(self.queue_dir / f"{sid}_{lid}.json", entry)
            pj["lastSubmit"] = entry
            write_json(self.dir(sid, lid) / "project.json", pj)
            return entry

    def queue(self) -> list[dict]:
        out = [read_json(p) for p in self.queue_dir.glob("*.json")] if self.queue_dir.is_dir() else []
        out = [e for e in out if e]
        out.sort(key=lambda e: e["submittedAt"])
        for e in out:
            e["key"] = f"{e['studentId']}_{e['lessonId']}"
        return out

    def queue_entry(self, key: str) -> dict | None:
        sid, _, lid = key.partition("_")
        if not valid_id(sid) or not valid_id(lid):
            return None
        e = read_json(self.queue_dir / f"{sid}_{lid}.json")
        if e:
            e["key"] = key
        return e

    def student_summaries(self, sid: str) -> dict:
        """lessonId -> short status of each of the student's projects (for the instructor's list)."""
        out = {}
        d = self.workspaces / sid
        if d.is_dir():
            for p in sorted(d.iterdir()):
                pj = read_json(p / "project.json")
                if pj:
                    out[pj["lessonId"]] = {"revision": pj["revision"], "lastBuild": pj["lastBuild"],
                                           "lastTest": pj["lastTest"], "lastSubmit": pj["lastSubmit"],
                                           "canSubmit": self.can_submit(sid, pj["lessonId"])}
        return out
