"""Plain-file storage helpers: atomic writes, JSON, id validation."""
import json
import os
import re
import tempfile
import threading
from pathlib import Path

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_JAVA_KEYWORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const", "continue",
    "default", "do", "double", "else", "enum", "extends", "final", "finally", "float", "for", "goto", "if",
    "implements", "import", "instanceof", "int", "interface", "long", "native", "new", "package", "private",
    "protected", "public", "return", "short", "static", "strictfp", "super", "switch", "synchronized", "this",
    "throw", "throws", "transient", "try", "void", "volatile", "while", "true", "false", "null",
}


def valid_id(s: object) -> bool:
    """Ids become path components and `<student>_<lesson>` queue keys: lowercase, digits, hyphen only."""
    return isinstance(s, str) and bool(_ID_RE.match(s))


def valid_java_identifier(s: object) -> bool:
    return isinstance(s, str) and bool(_IDENT_RE.match(s)) and s not in _JAVA_KEYWORDS


def atomic_write_bytes(path: Path, data: bytes, mode: int = 0o644) -> None:
    """Write to a temp file in the same directory, fsync, then rename over the target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    try:  # make the rename itself durable
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def atomic_write_text(path: Path, text: str, mode: int = 0o644) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode)


def write_json(path: Path, obj: object) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def read_json(path: Path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def lock_for(key: str) -> threading.RLock:
    """A process-wide lock per key (e.g. per project) for read-modify-write of JSON metadata."""
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())
