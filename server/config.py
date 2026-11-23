"""Server configuration, read from the environment (see /etc/robotics/server.env)."""
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from .storage import atomic_write_text

ROOT = Path(__file__).resolve().parent.parent  # the app dir when deployed, the repo root in development


@dataclass
class Config:
    data_dir: Path
    secret_key: str
    lib_dir: Path  # where robotics-api.jar etc. live
    api_jar: Path
    harness_jar: Path
    junit_jar: Path
    hamcrest_jar: Path
    web_ide: Path | None
    web_teacher: Path | None
    timeout_sec: int = 30
    max_heap_mb: int = 256
    max_output_kb: int = 256
    max_concurrent_jobs: int = 2
    max_source_kb: int = 256
    javac: str = "javac"
    java: str = "java"
    session_cookie_secure: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def classpath_libs(self) -> str:
        return os.pathsep.join(str(p) for p in (self.api_jar, self.junit_jar, self.hamcrest_jar))


def _find_libs(lib_dir: Path | None) -> tuple[Path, Path, Path, Path, Path]:
    """Deployed layout: everything flat in lib_dir. Development: api/build and .deps-cache."""
    if lib_dir is None:
        lib_dir = ROOT
    if (lib_dir / "robotics-api.jar").exists():
        return (lib_dir, lib_dir / "robotics-api.jar", lib_dir / "robotics-harness.jar",
                lib_dir / "junit-4.13.2.jar", lib_dir / "hamcrest-core-1.3.jar")
    return (lib_dir, lib_dir / "api/build/robotics-api.jar", lib_dir / "api/build/robotics-harness.jar",
            lib_dir / ".deps-cache/junit-4.13.2.jar", lib_dir / ".deps-cache/hamcrest-core-1.3.jar")


def _web_dir(lib_dir: Path, name: str) -> Path | None:
    for cand in (lib_dir / "web" / name / "index.html", lib_dir / "web" / name / "dist" / "index.html"):
        if cand.exists():
            return cand.parent
    return None


def load_config(overrides: dict | None = None) -> Config:
    env = dict(os.environ)
    env.update(overrides or {})
    data_dir = Path(env.get("ROBOTICS_DATA_DIR") or (ROOT / "data-dev")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    key = env.get("SECRET_KEY")
    if not key:  # development convenience: a persistent key beside the data (never in git)
        keyfile = data_dir / ".secret_key"
        if keyfile.exists():
            key = keyfile.read_text().strip()
        else:
            key = secrets.token_hex(32)
            atomic_write_text(keyfile, key, mode=0o600)

    lib_dir_env = env.get("ROBOTICS_LIB_DIR")
    lib_dir, api, harness, junit, hamcrest = _find_libs(Path(lib_dir_env) if lib_dir_env else None)

    def num(name: str, default: int) -> int:
        try:
            return int(env.get(name, default))
        except ValueError:
            return default

    return Config(
        data_dir=data_dir, secret_key=key, lib_dir=lib_dir,
        api_jar=api, harness_jar=harness, junit_jar=junit, hamcrest_jar=hamcrest,
        web_ide=_web_dir(lib_dir, "ide"), web_teacher=_web_dir(lib_dir, "teacher"),
        timeout_sec=num("BUILD_TIMEOUT_SEC", 30),
        max_heap_mb=num("BUILD_MAX_HEAP_MB", 256),
        max_output_kb=num("BUILD_MAX_OUTPUT_KB", 256),
        max_concurrent_jobs=num("MAX_CONCURRENT_JOBS", 2),
        javac=env.get("JAVAC", "javac"), java=env.get("JAVA", "java"),
    )
