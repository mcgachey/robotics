"""Lessons: lesson.json, starter/<Class>.java, tests/<Class>Test.java."""
from pathlib import Path

from .storage import atomic_write_text, lock_for, read_json, valid_id, valid_java_identifier, write_json

MAX_TEXT = 100_000


class LessonError(ValueError):
    pass


class Lessons:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir) / "lessons"

    def path(self, lesson_id: str) -> Path:
        return self.dir / lesson_id

    def meta(self, lesson_id: str) -> dict | None:
        if not valid_id(lesson_id):
            return None
        return read_json(self.path(lesson_id) / "lesson.json")

    def list(self) -> list[dict]:
        out = []
        if self.dir.is_dir():
            for d in sorted(self.dir.iterdir()):
                m = read_json(d / "lesson.json")
                if m:
                    out.append(m)
        return out

    def starter_path(self, meta: dict) -> Path:
        return self.path(meta["id"]) / "starter" / f"{meta['className']}.java"

    def tests_dir(self, meta: dict) -> Path:
        return self.path(meta["id"]) / "tests"

    def test_class(self, meta: dict) -> str:
        return meta["className"] + "Test"

    def full(self, lesson_id: str) -> dict | None:
        m = self.meta(lesson_id)
        if not m:
            return None
        starter = self.starter_path(m)
        test = self.tests_dir(m) / f"{self.test_class(m)}.java"
        return {**m,
                "starter": starter.read_text("utf-8") if starter.exists() else "",
                "tests": test.read_text("utf-8") if test.exists() else "",
                "testClassName": self.test_class(m)}

    def save(self, lesson_id: str, title: str, class_name: str, starter: str, tests: str,
             target_phase: int = 1, api_version: int = 0, create: bool = True) -> dict:
        if not valid_id(lesson_id):
            raise LessonError("The lesson id may use lowercase letters, digits and '-' (up to 40).")
        title = (title or "").strip()
        if not title or len(title) > 120:
            raise LessonError("Enter a lesson title.")
        if not valid_java_identifier(class_name):
            raise LessonError("The class name must be a valid Java name, like HelloWorld.")
        if not isinstance(starter, str) or not isinstance(tests, str):
            raise LessonError("The starter code and the tests must be text.")
        if len(starter) > MAX_TEXT or len(tests) > MAX_TEXT:
            raise LessonError("The starter code or tests are too long.")
        if not isinstance(target_phase, int) or not isinstance(api_version, int):
            raise LessonError("targetPhase and apiVersion must be whole numbers.")
        with lock_for("lessons"):
            existing = self.meta(lesson_id)
            if create and existing:
                raise LessonError("A lesson with that id already exists.")
            if not create:
                if not existing:
                    raise KeyError(lesson_id)
                if existing["className"] != class_name:
                    raise LessonError("The class name of an existing lesson cannot be changed "
                                      "(students' projects already use it).")
            meta = {"id": lesson_id, "title": title, "className": class_name,
                    "targetPhase": target_phase, "apiVersion": api_version}
            d = self.path(lesson_id)
            atomic_write_text(d / "starter" / f"{class_name}.java", starter)
            atomic_write_text(d / "tests" / f"{class_name}Test.java", tests)
            write_json(d / "lesson.json", meta)  # last: the lesson exists once its files do
        return meta
