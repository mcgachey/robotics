"""Lessons are source: lessons/<id>/{lesson.json, starter/<Class>.java, tests/<Class>Test.java} in the repo.

The server only reads them. The one piece of runtime lesson state is which lessons are enabled
(data/lessons-enabled.json); a lesson that is not listed there is disabled and hidden from students.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .storage import atomic_write_text, lock_for, read_json, valid_id, valid_java_identifier

log = logging.getLogger("robotics")

ENABLED_FILE = "lessons-enabled.json"


class Lessons:
    def __init__(self, lessons_dir: Path, data_dir: Path):
        self.dir = Path(lessons_dir)
        self.enabled_path = Path(data_dir) / ENABLED_FILE
        self._warned: set[str] = set()

    # --- definitions (read-only, from the source tree) -------------------------------
    def path(self, lesson_id: str) -> Path:
        return self.dir / lesson_id

    def _problem(self, d: Path, m) -> str | None:
        if not isinstance(m, dict):
            return "lesson.json is not a JSON object"
        if m.get("id") != d.name or not valid_id(d.name):
            return "id must equal the directory name (lowercase letters, digits, '-')"
        if not isinstance(m.get("title"), str) or not m["title"].strip():
            return "missing title"
        if not valid_java_identifier(m.get("className")):
            return "className is not a valid Java name"
        for k in ("targetPhase", "apiVersion"):
            if not isinstance(m.get(k), int) or isinstance(m.get(k), bool):
                return f"{k} must be a whole number"
        t = m.get("timeout")
        if t is not None and (isinstance(t, bool) or not isinstance(t, (int, float)) or not 0 < t < 3600):
            return "timeout must be a number of seconds greater than 0"
        if not (d / "starter" / f"{m['className']}.java").is_file():
            return f"missing starter/{m['className']}.java"
        if not (d / "tests" / f"{m['className']}Test.java").is_file():
            return f"missing tests/{m['className']}Test.java"
        return None

    def meta(self, lesson_id: str) -> dict | None:
        """A defined lesson's metadata, whether or not it is enabled; None if undefined or invalid."""
        if not valid_id(lesson_id):
            return None
        d = self.path(lesson_id)
        try:
            m = read_json(d / "lesson.json")
        except (ValueError, OSError) as e:
            m, problem = None, f"cannot read lesson.json ({e})"
        else:
            problem = None if m is None else self._problem(d, m)
        if m is None and problem is None:
            return None  # no such lesson
        if problem:
            if lesson_id not in self._warned:
                self._warned.add(lesson_id)
                log.warning("Skipping lesson %s: %s", lesson_id, problem)
            return None
        return m

    def list(self) -> list[dict]:
        """All defined lessons (valid ones only), in id order."""
        out = []
        if self.dir.is_dir():
            for d in sorted(self.dir.iterdir()):
                if d.is_dir():
                    m = self.meta(d.name)
                    if m:
                        out.append(m)
        return out

    def starter_path(self, meta: dict) -> Path:
        return self.path(meta["id"]) / "starter" / f"{meta['className']}.java"

    def tests_dir(self, meta: dict) -> Path:
        return self.path(meta["id"]) / "tests"

    def test_class(self, meta: dict) -> str:
        return meta["className"] + "Test"

    # --- enabled state (runtime data) -------------------------------------------------
    def enabled_ids(self) -> set[str]:
        try:
            d = read_json(self.enabled_path, {})
        except (ValueError, OSError):
            log.warning("Cannot read %s; treating every lesson as disabled", self.enabled_path)
            return set()
        ids = d.get("enabled") if isinstance(d, dict) else None
        return {i for i in ids if isinstance(i, str)} if isinstance(ids, list) else set()

    def is_enabled(self, lesson_id: str) -> bool:
        return lesson_id in self.enabled_ids()

    def set_enabled(self, lesson_id: str, enabled: bool) -> None:
        if not self.meta(lesson_id):
            raise KeyError(lesson_id)
        with lock_for("lessons-enabled"):
            ids = self.enabled_ids()
            ids.add(lesson_id) if enabled else ids.discard(lesson_id)
            atomic_write_text(self.enabled_path, json.dumps({"enabled": sorted(ids)}, indent=2) + "\n")

    def list_enabled(self) -> list[dict]:
        on = self.enabled_ids()
        return [m for m in self.list() if m["id"] in on]

    def list_with_state(self) -> list[dict]:
        on = self.enabled_ids()
        return [{**m, "enabled": m["id"] in on} for m in self.list()]
