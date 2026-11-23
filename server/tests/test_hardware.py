"""Hardware tab: droids from the board controller, Deploy/Stop, assignments. The controller is a fake HTTP server."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from server.app import create_app
from server.tests.conftest import Api, STARTER
from server.tests.test_api import job, save

DROID = "f481850ee93c"

DRIVE = STARTER.replace("// TODO: log \"Hello, world!\"", """
        robot.rightDrive().setDirection(DriveMotor.Direction.REVERSE);
        robot.leftDrive().setPower(0.5);
        robot.rightDrive().setPower(0.5);
        robot.beep(0);
        robot.log("driving");
        Thread.sleep(%d);""").replace("public void run(Robot robot) {", "public void run(Robot robot) throws Exception {")


def drive(ms):
    return DRIVE % ms


class FakeController:
    def __init__(self):
        self.boards = [
            {"device_id": DROID, "role": "droid", "name": "r2t2", "online": True, "port": "/dev/ttyUSB0",
             "info": {"firmware_version": "0.3.0"}},
            {"device_id": "aaaabbbbcccc", "role": "droid", "name": "offline-one", "online": False},
            {"device_id": "beac0nbeac0n", "role": "beacon", "name": "beacon", "online": True},
        ]
        self.commands = []  # (board, cmd, args)
        self.lock = threading.Lock()
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, obj):
                data = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/api/boards":
                    return self._send(200, fake.boards)
                self._send(404, {"error": "not_found", "message": "no"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                args = json.loads(self.rfile.read(n) or b"{}")
                parts = self.path.split("/")  # '', api, boards, <id>, commands, <cmd>
                with fake.lock:
                    fake.commands.append((parts[3], parts[5], args))
                self._send(200, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def cmds(self, name=None):
        with self.lock:
            return [(b, c, a) for b, c, a in self.commands if name is None or c == name]

    def wait_for(self, name, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            if self.cmds(name):
                return
            time.sleep(0.05)
        raise AssertionError(f"controller never got {name}: {self.commands}")


@pytest.fixture
def controller():
    c = FakeController()
    yield c
    c.server.shutdown()


@pytest.fixture
def hw_env(env, controller):
    return {**env, "CONTROLLER_URL": controller.url, "BUILD_TIMEOUT_SEC": "20", "DEPLOY_MAX_SEC": "20"}


@pytest.fixture
def hw_app(hw_env):
    return create_app(hw_env)


@pytest.fixture
def teach(hw_app):
    hw_app.robotics.accounts.create_instructor("teach", "secret1")
    a = Api(hw_app)
    a.login("teach", "secret1")
    a.patch("/api/instructor/lessons/lesson0", {"enabled": True})
    return a


@pytest.fixture
def ada(hw_app, teach):
    teach.post("/api/instructor/students", {"name": "Ada", "username": "ada", "password": "pw1234"}, 201)
    a = Api(hw_app)
    a.login("ada", "pw1234")
    return a


def deploy(teach, ada_id, rev, status=202, board=DROID):
    return teach.post(f"/api/instructor/hardware/{board}/deploy",
                      {"studentId": ada_id, "lessonId": "lesson0", "revision": rev}, status)


def test_overview_lists_only_droids_and_students_with_builds(teach, ada, controller):
    ov = teach.get("/api/instructor/hardware")
    assert ov["controller"]["ok"]
    assert [d["id"] for d in ov["droids"]] == [DROID, "aaaabbbbcccc"], "online droids first, no beacons"
    assert ov["droids"][0]["assignment"] is None and ov["droids"][0]["run"] is None
    assert ov["students"] == []

    save(ada, drive(1))
    assert job(ada, "build")["status"] == "passed"
    save(ada, drive(2))
    assert job(ada, "build")["status"] == "passed"
    (s,) = teach.get("/api/instructor/hardware")["students"]
    assert s["name"] == "Ada" and {b["revision"] for b in s["builds"]} == {1, 2}
    assert s["builds"][0]["lessonTitle"]


def test_instructor_builds_of_submissions_can_be_deployed(hw_app, teach, ada, controller):
    from server.storage import read_json, write_json
    sid = ada.get("/api/me")["id"]
    save(ada, STARTER.replace("// TODO: log \"Hello, world!\"", "robot.log(\"Hello, world!\");"))
    assert job(ada, "test")["status"] == "passed"
    ada.post("/api/me/projects/lesson0/submit")
    # forget the student's own build of that revision, as if only the instructor had built it
    pjson = hw_app.robotics.projects.dir(sid, "lesson0") / "project.json"
    pj = read_json(pjson)
    pj["goodBuilds"] = {}
    write_json(pjson, pj)
    assert teach.get("/api/instructor/hardware")["students"] == []
    (q,) = teach.get("/api/instructor/queue")
    assert teach.wait_job(teach.post(f"/api/instructor/queue/{q['key']}/build", status=202)["jobId"])["status"] == "passed"
    (s,) = teach.get("/api/instructor/hardware")["students"]
    assert [b["revision"] for b in s["builds"]] == [q["revision"]]


def test_deploy_runs_the_built_code_on_the_selected_droid_and_stops_it(teach, ada, controller):
    sid = ada.get("/api/me")["id"]
    save(ada, drive(400))
    rev = job(ada, "build")["revision"]
    jid = deploy(teach, sid, rev)["jobId"]
    j = teach.wait_job(jid)
    assert j["status"] == "passed", j
    assert j["kind"] == "deploy" and j["boardId"] == DROID
    out = teach.get(f"/api/jobs/{jid}")["output"]
    assert "driving" in out
    assert f"firmware 0.3.0" in out and f"(revision {rev})" in out, out

    boards = {b for b, _, _ in controller.cmds()}
    assert boards == {DROID}, "only the selected droid was driven"
    motors = [a for _, c, a in controller.cmds("motor")]
    assert {"motor": "left", "backward": False, "speed": 0xb0, "ramp_ms": 100} in motors
    assert {"motor": "right", "backward": True, "speed": 0xb0, "ramp_ms": 100} not in motors, \
        "REVERSE on a right motor wired reversed drives forward"
    assert {"motor": "right", "backward": False, "speed": 0xb0, "ramp_ms": 100} in motors
    assert controller.cmds("beep")
    assert controller.cmds("stop"), "the harness always sends a final stop"
    assert motors[-1]["speed"] == 0 and motors[-2]["speed"] == 0, "both motors stopped at the end"

    ov = teach.get("/api/instructor/hardware")
    a = ov["droids"][0]["assignment"]
    assert (a["studentName"], a["lessonId"], a["revision"]) == ("Ada", "lesson0", rev)
    assert ov["droids"][0]["run"] is None, "finished"
    assert ov["droids"][1]["assignment"] is None


def test_assignment_survives_restart_and_can_be_cleared(hw_env, hw_app, teach, ada, controller):
    sid = ada.get("/api/me")["id"]
    save(ada, drive(1))
    rev = job(ada, "build")["revision"]
    teach.wait_job(deploy(teach, sid, rev)["jobId"])
    t2 = Api(create_app(hw_env))
    t2.login("teach", "secret1")
    assert t2.get("/api/instructor/hardware")["droids"][0]["assignment"]["revision"] == rev
    t2.call("DELETE", f"/api/instructor/hardware/{DROID}/assignment", status=200)
    assert t2.get("/api/instructor/hardware")["droids"][0]["assignment"] is None


def test_stop_kills_the_program_and_stops_the_droid(teach, ada, controller):
    sid = ada.get("/api/me")["id"]
    save(ada, drive(60000))
    rev = job(ada, "build")["revision"]
    jid = deploy(teach, sid, rev)["jobId"]
    controller.wait_for("motor")
    assert teach.get("/api/instructor/hardware")["droids"][0]["run"]["jobId"] == jid
    # a second program on the same droid is refused, another droid is not
    teach.post(f"/api/instructor/hardware/{DROID}/deploy",
               {"studentId": sid, "lessonId": "lesson0", "revision": rev}, 409)
    teach.post(f"/api/instructor/hardware/{DROID}/stop")
    j = teach.wait_job(jid)
    assert j["status"] == "cancelled"
    assert controller.cmds("stop"), "stop reaches the droid even though the JVM was killed"
    assert teach.get("/api/instructor/hardware")["droids"][0]["run"] is None


def test_deploy_validation(teach, ada, controller):
    sid = ada.get("/api/me")["id"]
    save(ada, drive(1))
    rev = job(ada, "build")["revision"]
    deploy(teach, sid, rev + 5, 409)                                 # never built
    deploy(teach, sid, rev, 409, board="aaaabbbbcccc")               # offline
    deploy(teach, sid, rev, 404, board="nonexistent")                # unknown droid
    deploy(teach, sid, rev, 404, board="..%2Fx")                     # path tricks
    teach.post(f"/api/instructor/hardware/{DROID}/deploy", {"studentId": "nope", "lessonId": "lesson0", "revision": rev}, 404)
    teach.post(f"/api/instructor/hardware/{DROID}/deploy", {"studentId": sid, "lessonId": "lesson0", "revision": "1"}, 400)
    assert controller.cmds() == []


def test_students_cannot_use_hardware(teach, ada, controller):
    ada.get("/api/instructor/hardware", status=403)
    ada.post(f"/api/instructor/hardware/{DROID}/stop", status=403)


def test_controller_down_is_reported(hw_env, teach, ada, controller):
    controller.server.shutdown()
    controller.server.server_close()
    ov = teach.get("/api/instructor/hardware")
    assert ov["controller"]["ok"] is False and "board controller" in ov["controller"]["error"]
    assert ov["droids"] == []
    sid = ada.get("/api/me")["id"]
    save(ada, drive(1))
    rev = job(ada, "build")["revision"]
    deploy(teach, sid, rev, 503)
