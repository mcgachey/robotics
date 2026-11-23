"""Build service on the command line (plan step 3): python -m server.buildcli FILE.java --lesson-dir DIR [--test]

Prints the structured result as JSON. Handy for measuring Lesson 0 build/test latency on the Pi.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from .builder import BuildService
from .config import load_config
from .jobs import Job


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", type=Path)
    ap.add_argument("--lesson-dir", type=Path, required=True, help="a lessons/<id> directory")
    ap.add_argument("--test", action="store_true", help="also run the lesson's tests")
    ap.add_argument("--raw", action="store_true", help="include the raw output")
    args = ap.parse_args(argv)

    lesson = json.loads((args.lesson_dir / "lesson.json").read_text())
    cfg = load_config()

    class _Lessons:  # the on-disk layout of a lesson, without needing a data dir
        def tests_dir(self, meta): return args.lesson_dir / "tests"
        def test_class(self, meta): return meta["className"] + "Test"

    with tempfile.TemporaryDirectory(prefix="buildcli-") as tmp:
        job = Job("cli", "test" if args.test else "build", "cli", "cli", "cli", lesson["id"], 0, Path(tmp),
                  class_name=lesson["className"], api_version=lesson.get("apiVersion", 0),
                  output_cap=cfg.max_output_kb * 1024)
        BuildService(cfg, _Lessons()).execute(job, args.source, lesson)
        out = job.to_dict(include_output=args.raw)
    print(json.dumps(out, indent=2))
    return 0 if out["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
