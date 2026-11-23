import json
import time
from pathlib import Path

import pytest

from server.app import create_app

REPO = Path(__file__).resolve().parents[2]
LESSON0 = REPO / "lessons" / "lesson0"
STARTER = (LESSON0 / "starter" / "HelloWorld.java").read_text()
TESTS = (LESSON0 / "tests" / "HelloWorldTest.java").read_text()
GOOD = STARTER.replace('// TODO: log "Hello, world!"', 'robot.log("Hello, world!");')
SYNTAX_ERROR = GOOD.replace('robot.log("Hello, world!");', 'robot.log("Hello, world!")')
INFINITE = STARTER.replace('// TODO: log "Hello, world!"', 'while (true) { }')
FLOOD = STARTER.replace('// TODO: log "Hello, world!"', 'while (true) { System.out.println("spam spam spam spam"); }')
EXIT = STARTER.replace('// TODO: log "Hello, world!"', 'System.exit(3);')


@pytest.fixture
def env(tmp_path):
    return {"ROBOTICS_DATA_DIR": str(tmp_path / "data"), "BUILD_TIMEOUT_SEC": "4",
            "BUILD_MAX_OUTPUT_KB": "32", "BUILD_MAX_HEAP_MB": "128",
            "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000"}


@pytest.fixture
def app(env):
    return create_app(env)


class Api:
    """A logged-in test client with JSON helpers."""
    def __init__(self, app):
        self.c = app.test_client()

    def call(self, method, path, data=None, status=None):
        r = self.c.open(path, method=method, json=data)
        if status is not None:
            assert r.status_code == status, f"{method} {path} -> {r.status_code} {r.get_data(as_text=True)[:300]}"
        return r

    def get(self, path, status=200): return self.call("GET", path, status=status).get_json()
    def post(self, path, data=None, status=200): return self.call("POST", path, data or {}, status).get_json()
    def put(self, path, data=None, status=200): return self.call("PUT", path, data or {}, status).get_json()
    def patch(self, path, data=None, status=200): return self.call("PATCH", path, data or {}, status).get_json()

    def login(self, user, pw, status=200):
        return self.post("/api/login", {"username": user, "password": pw}, status)

    def wait_running_tests(self, jid, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            j = self.get(f"/api/jobs/{jid}")
            if "Running the tests" in j.get("output", "") or j["status"] != "running":
                return j
            time.sleep(0.05)
        raise AssertionError("job never reached the test run")

    def wait_job(self, jid, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            j = self.get(f"/api/jobs/{jid}")
            if j["status"] != "running":
                return j
            time.sleep(0.05)
        raise AssertionError("job did not finish")


@pytest.fixture
def teacher(app):
    app.robotics.accounts.create_teacher("teach", "secret1")
    a = Api(app)
    a.login("teach", "secret1")
    return a


@pytest.fixture
def lesson0(teacher):
    teacher.post("/api/teacher/lessons", {"id": "lesson0", "title": "Lesson 0", "className": "HelloWorld",
                                          "starter": STARTER, "tests": TESTS}, 201)


@pytest.fixture
def ada(app, teacher, lesson0):
    teacher.post("/api/teacher/students", {"name": "Ada", "username": "ada", "password": "pw1234"}, 201)
    a = Api(app)
    a.login("ada", "pw1234")
    return a
