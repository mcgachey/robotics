"""Teacher and student accounts: plain JSON files, hashed passwords (D4, D5)."""
import re
import secrets
import shutil
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from .storage import lock_for, read_json, write_json

LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
_HASH_METHOD = "pbkdf2:sha256"
_DUMMY_HASH = generate_password_hash("not-a-password", method=_HASH_METHOD)


class AccountError(ValueError):
    """A user-facing validation problem."""


def _check_password(pw: object) -> str:
    if not isinstance(pw, str) or len(pw) < 4:
        raise AccountError("The password must be at least 4 characters.")
    if len(pw) > 200:
        raise AccountError("The password is too long.")
    return pw


class Accounts:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.teacher_file = self.data_dir / "teacher.json"
        self.students_dir = self.data_dir / "students"

    # --- teacher ---------------------------------------------------------
    def teacher(self) -> dict | None:
        return read_json(self.teacher_file)

    def create_teacher(self, login: str, password: str, name: str = "Teacher", force: bool = False) -> dict:
        login = (login or "").strip().lower()
        if not LOGIN_RE.match(login):
            raise AccountError("The username may use lowercase letters, digits, '.', '-' and '_'.")
        _check_password(password)
        with lock_for("accounts"):
            if self.teacher_file.exists() and not force:
                raise AccountError("A teacher account already exists.")
            if self.find_student_by_login(login):
                raise AccountError("That username is used by a student.")
            rec = {"id": "teacher", "login": login, "name": name,
                   "passwordHash": generate_password_hash(password, method=_HASH_METHOD)}
            write_json(self.teacher_file, rec)
        return rec

    # --- students --------------------------------------------------------
    @staticmethod
    def public(rec: dict) -> dict:
        return {k: v for k, v in rec.items() if k != "passwordHash"}

    def student(self, student_id: str) -> dict | None:
        if not re.match(r"^s[0-9a-f]{8}$", student_id or ""):
            return None
        return read_json(self.students_dir / student_id / "student.json")

    def students(self) -> list[dict]:
        out = []
        if self.students_dir.is_dir():
            for d in sorted(self.students_dir.iterdir()):
                rec = read_json(d / "student.json")
                if rec:
                    out.append(rec)
        out.sort(key=lambda r: (r["name"].lower(), r["login"]))
        return out

    def find_student_by_login(self, login: str) -> dict | None:
        login = (login or "").strip().lower()
        for rec in self.students():
            if rec["login"] == login:
                return rec
        return None

    def create_student(self, name: str, login: str, password: str) -> dict:
        name = (name or "").strip()
        login = (login or "").strip().lower()
        if not name or len(name) > 80:
            raise AccountError("Enter the student's name (up to 80 characters).")
        if not LOGIN_RE.match(login):
            raise AccountError("The username may use lowercase letters, digits, '.', '-' and '_' (up to 32).")
        _check_password(password)
        with lock_for("accounts"):
            if self.find_student_by_login(login) or (self.teacher() or {}).get("login") == login:
                raise AccountError("That username is already taken.")
            sid = "s" + secrets.token_hex(4)
            rec = {"id": sid, "name": name, "login": login, "enabled": True,
                   "passwordHash": generate_password_hash(password, method=_HASH_METHOD)}
            write_json(self.students_dir / sid / "student.json", rec)
        return rec

    def update_student(self, student_id: str, enabled=None, password=None, name=None) -> dict:
        with lock_for("accounts"):
            rec = self.student(student_id)
            if not rec:
                raise KeyError(student_id)
            if enabled is not None:
                if not isinstance(enabled, bool):
                    raise AccountError("'enabled' must be true or false.")
                rec["enabled"] = enabled
            if password is not None:
                rec["passwordHash"] = generate_password_hash(_check_password(password), method=_HASH_METHOD)
            if name is not None:
                name = str(name).strip()
                if not name or len(name) > 80:
                    raise AccountError("Enter the student's name (up to 80 characters).")
                rec["name"] = name
            write_json(self.students_dir / student_id / "student.json", rec)
        return rec

    # --- login -----------------------------------------------------------
    def authenticate(self, login: str, password: str) -> tuple[str, dict] | None:
        """Return ("teacher"|"student", record) for valid credentials of an enabled account."""
        login = (login or "").strip().lower()
        if not isinstance(password, str):
            return None
        teacher = self.teacher()
        if teacher and teacher["login"] == login:
            return ("teacher", teacher) if check_password_hash(teacher["passwordHash"], password) else None
        rec = self.find_student_by_login(login)
        if not rec:
            check_password_hash(_DUMMY_HASH, password)  # keep timing similar
            return None
        if check_password_hash(rec["passwordHash"], password) and rec.get("enabled", True):
            return ("student", rec)
        return None
