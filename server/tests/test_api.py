import shutil
import time
from pathlib import Path

from server.app import create_app
from server.tests.conftest import Api, GOOD, INFINITE, REPO, STARTER, SYNTAX_ERROR


def save(a, src, lid="lesson0"):
    return a.put(f"/api/me/projects/{lid}/source", {"source": src})


def job(a, kind, lid="lesson0"):
    jid = a.post(f"/api/me/projects/{lid}/{kind}", status=202)["jobId"]
    return a.wait_job(jid)


# --- auth and roles ------------------------------------------------------------
def test_login_logout_and_me(app, teacher, ada):
    assert ada.get("/api/me")["role"] == "student"
    ada.post("/api/logout")
    ada.get("/api/me", 401)
    Api(app).login("ada", "wrong", 401)
    Api(app).login("nobody", "pw1234", 401)


def test_anonymous_gets_401_everywhere(app, ada):
    anon = Api(app)
    for m, p in [("GET", "/api/lessons"), ("GET", "/api/me/projects/lesson0"), ("GET", "/api/teacher/queue"),
                 ("GET", "/api/jobs/x"), ("POST", "/api/me/projects/lesson0/build")]:
        assert anon.call(m, p).status_code == 401, p


def test_student_cannot_use_teacher_routes(ada):
    for m, p in [("GET", "/api/teacher/students"), ("POST", "/api/teacher/students"), ("GET", "/api/teacher/lessons"),
                 ("PATCH", "/api/teacher/lessons/lesson0"), ("GET", "/api/teacher/queue"),
                 ("PATCH", "/api/teacher/students/sabcdef01"),
                 ("GET", "/api/teacher/students/sabcdef01/projects/lesson0"),
                 ("POST", "/api/teacher/queue/x_y/build"), ("POST", "/api/teacher/queue/x_y/test")]:
        assert ada.call(m, p, {}).status_code == 403, (m, p)


def test_teacher_cannot_use_student_routes(teacher, lesson0):
    assert teacher.call("GET", "/api/me/projects/lesson0").status_code == 403


def test_disabled_student_loses_access_immediately(app, teacher, ada):
    sid = ada.get("/api/me")["id"]
    teacher.patch(f"/api/teacher/students/{sid}", {"enabled": False})
    ada.get("/api/me", 401)
    Api(app).login("ada", "pw1234", 401)
    teacher.patch(f"/api/teacher/students/{sid}", {"enabled": True})
    Api(app).login("ada", "pw1234")


def test_password_reset_and_validation(app, teacher, ada):
    sid = ada.get("/api/me")["id"]
    teacher.patch(f"/api/teacher/students/{sid}", {"password": "newpass"})
    Api(app).login("ada", "pw1234", 401)
    Api(app).login("ada", "newpass")
    teacher.post("/api/teacher/students", {"name": "Dup", "username": "ada", "password": "xxxxxx"}, 400)
    teacher.post("/api/teacher/students", {"name": "X", "username": "bad name", "password": "xxxxxx"}, 400)
    teacher.post("/api/teacher/students", {"name": "X", "username": "xx", "password": "1"}, 400)


def test_passwords_are_hashed_on_disk(app, ada):
    raw = (app.robotics.cfg.data_dir / "teacher.json").read_text()
    assert "secret1" not in raw and "pbkdf2" in raw


# --- lessons and projects -------------------------------------------------------------
def test_project_created_from_starter_and_starter_edits_do_not_touch_it(app, teacher, ada):
    assert ada.get("/api/me/projects/lesson0")["source"] == STARTER
    # Simulate a redeploy with a changed starter (the lesson files are source, never edited at runtime).
    app.robotics.lessons.dir = Path(shutil.copytree(app.robotics.lessons.dir, app.robotics.cfg.data_dir / "l2"))
    (app.robotics.lessons.dir / "lesson0" / "starter" / "HelloWorld.java").write_text("// changed")
    assert ada.get("/api/me/projects/lesson0")["source"] == STARTER
    ada.get("/api/me/projects/nope", 404)


def test_lessons_start_disabled_and_teacher_toggles_them(app, teacher):
    t = teacher.get("/api/teacher/lessons")
    assert [(l["id"], l["enabled"]) for l in t] == [("lesson0", False)]
    teacher.post("/api/teacher/students", {"name": "Ada", "username": "ada", "password": "pw1234"}, 201)
    ada = Api(app)
    ada.login("ada", "pw1234")
    assert ada.get("/api/lessons") == []
    for m, p in [("GET", "/api/me/projects/lesson0"), ("PUT", "/api/me/projects/lesson0/source"),
                 ("POST", "/api/me/projects/lesson0/build"), ("POST", "/api/me/projects/lesson0/test"),
                 ("POST", "/api/me/projects/lesson0/submit")]:
        assert ada.call(m, p, {"source": "x"}).status_code == 404, (m, p)
    assert teacher.patch("/api/teacher/lessons/lesson0", {"enabled": True})["enabled"] is True
    assert [l["id"] for l in ada.get("/api/lessons")] == ["lesson0"]
    ada.get("/api/me/projects/lesson0")
    teacher.patch("/api/teacher/lessons/lesson0", {"enabled": False})
    assert ada.get("/api/lessons") == []
    ada.get("/api/me/projects/lesson0", 404)
    teacher.patch("/api/teacher/lessons/lesson0", {"enabled": "yes"}, 400)
    teacher.patch("/api/teacher/lessons/nope", {"enabled": True}, 404)
    # the choice is stored in the data directory and survives a restart
    app2 = create_app({"ROBOTICS_DATA_DIR": str(app.robotics.cfg.data_dir)})
    assert app2.robotics.lessons.enabled_ids() == set()
    teacher.patch("/api/teacher/lessons/lesson0", {"enabled": True})
    assert create_app({"ROBOTICS_DATA_DIR": str(app.robotics.cfg.data_dir)}).robotics.lessons.enabled_ids() == {"lesson0"}


def test_disabling_keeps_student_work(app, teacher, ada):
    save(ada, GOOD)
    teacher.patch("/api/teacher/lessons/lesson0", {"enabled": False})
    ada.get("/api/me/projects/lesson0", 404)
    teacher.patch("/api/teacher/lessons/lesson0", {"enabled": True})
    assert ada.get("/api/me/projects/lesson0")["source"] == GOOD


def test_invalid_lesson_directories_are_skipped(tmp_path):
    from server.lessons import Lessons
    root = tmp_path / "lessons"
    shutil.copytree(REPO / "lessons" / "lesson0", root / "lesson0")
    shutil.copytree(REPO / "lessons" / "lesson0", root / "wrong-name")  # id != directory name
    (root / "broken").mkdir()
    (root / "broken" / "lesson.json").write_text("{not json")
    (root / "empty").mkdir()
    ls = Lessons(root, tmp_path / "data")
    assert [m["id"] for m in ls.list()] == ["lesson0"]
    assert ls.meta("broken") is None and ls.meta("../lesson0") is None


def test_other_students_cannot_see_my_work(app, teacher, ada):
    save(ada, GOOD)
    teacher.post("/api/teacher/students", {"name": "Bob", "username": "bob", "password": "pw1234"}, 201)
    bob = Api(app)
    bob.login("bob", "pw1234")
    assert bob.get("/api/me/projects/lesson0")["source"] == STARTER  # his own, not Ada's
    jid = ada.post("/api/me/projects/lesson0/build", status=202)["jobId"]
    bob.get(f"/api/jobs/{jid}", 404)
    bob.get(f"/api/jobs/{jid}/events", 404)
    bob.post(f"/api/me/jobs/{jid}/stop", status=404)
    ada.wait_job(jid)
    bob.get(f"/api/jobs/{jid}", 404)
    teacher.get(f"/api/jobs/{jid}")  # teacher may


def test_path_tricks_rejected(ada):
    ada.get("/api/jobs/..%2F..%2Fetc", 404)
    ada.get("/api/me/projects/..%2Fx", 404)


# --- the student loop (acceptance steps 4-6) ---------------------------------------------
def test_student_loop(app, ada):
    j = job(ada, "build")
    assert j["status"] == "passed" and ada.get("/api/me/projects/lesson0")["canSubmit"] is False

    t = job(ada, "test")
    assert t["status"] == "failed" and t["reason"] == "test_failure"
    assert t["artifactBuildId"] == j["id"], "Test reuses the successful build of this exact revision"
    assert "Hello, world!" in t["tests"][0]["message"]
    ada.post("/api/me/projects/lesson0/submit", status=409)

    save(ada, SYNTAX_ERROR)
    bad = job(ada, "build")
    assert bad["reason"] == "compile_error" and bad["diagnostics"][0]["line"] == 6
    proj = ada.get("/api/me/projects/lesson0")
    assert proj["lastBuild"]["status"] == "failed"
    kept = proj["lastGoodBuild"]["jobId"]
    assert (app.robotics.cfg.data_dir / "builds" / kept / "artifact.jar").exists(), "last good artifact intact"

    save(ada, GOOD)
    assert job(ada, "build")["status"] == "passed"
    assert ada.get("/api/me/projects/lesson0")["canSubmit"] is False
    t = job(ada, "test")
    assert t["status"] == "passed"
    assert ada.get("/api/me/projects/lesson0")["canSubmit"] is True


def test_editing_after_a_passing_test_closes_the_submit_gate(ada):
    save(ada, GOOD)
    assert job(ada, "test")["status"] == "passed"
    assert save(ada, GOOD + "\n// tweak")["canSubmit"] is False
    ada.post("/api/me/projects/lesson0/submit", status=409)
    save(ada, GOOD)  # back to the tested text: gate reopens
    assert ada.get("/api/me/projects/lesson0")["canSubmit"] is True


def test_build_snapshots_source_and_reuses_identical_revisions(app, ada):
    save(ada, GOOD)
    a = job(ada, "build")
    b = job(ada, "build")
    assert a["revision"] == b["revision"] == 1
    save(ada, GOOD + "\n")
    assert job(ada, "build")["revision"] == 2
    d = app.robotics.cfg.data_dir / "workspaces"
    revs = list(d.glob("*/lesson0/revisions/*/HelloWorld.java"))
    assert len(revs) == 2 and all(not (r.stat().st_mode & 0o222) for r in revs), "snapshots are read-only"


def test_one_active_job_per_student_and_stop(ada):
    save(ada, INFINITE)
    jid = ada.post("/api/me/projects/lesson0/test", status=202)["jobId"]
    r = ada.call("POST", "/api/me/projects/lesson0/build", {})
    assert r.status_code == 409 and "already have" in r.get_json()["error"]
    assert ada.get("/api/me/projects/lesson0")["activeJobId"] == jid
    ada.wait_running_tests(jid)
    ada.post(f"/api/me/jobs/{jid}/stop")
    j = ada.wait_job(jid, 10)
    assert j["status"] == "cancelled"
    assert job(ada, "build")["status"] == "passed"  # free to start again


def test_infinite_loop_killed_and_server_stays_responsive(ada):
    save(ada, INFINITE)
    jid = ada.post("/api/me/projects/lesson0/test", status=202)["jobId"]
    t0 = time.time()
    ada.get("/api/me")
    assert time.time() - t0 < 1
    j = ada.wait_job(jid, 20)
    assert j["reason"] == "timeout" and "ran too long" in j["message"]


def test_global_concurrency_limit(app, teacher, ada):
    teacher.post("/api/teacher/students", {"name": "B", "username": "b1", "password": "pw1234"}, 201)
    teacher.post("/api/teacher/students", {"name": "C", "username": "c1", "password": "pw1234"}, 201)
    clients = [ada]
    for u in ("b1", "c1"):
        a = Api(app)
        a.login(u, "pw1234")
        clients.append(a)
    for a in clients:
        save(a, INFINITE)
    r = [a.call("POST", "/api/me/projects/lesson0/test", {}) for a in clients]
    assert [x.status_code for x in r] == [202, 202, 503]
    for a, x in zip(clients, r):
        if x.status_code == 202:
            a.post(f"/api/me/jobs/{x.get_json()['jobId']}/stop")


# --- events (SSE) ---------------------------------------------------------------------------
def test_sse_streams_and_ends_with_done(ada):
    save(ada, GOOD)
    jid = ada.post("/api/me/projects/lesson0/test", status=202)["jobId"]
    body = ada.call("GET", f"/api/jobs/{jid}/events", status=200).get_data(as_text=True)
    assert "event: status" in body and "event: done" in body and "Compiling HelloWorld.java" in body


def test_finished_job_events_replay_from_disk_after_restart(env, app, ada):
    save(ada, GOOD)
    jid = job(ada, "build")["id"]
    app2 = create_app(env)
    c = Api(app2)
    c.login("ada", "pw1234")
    body = c.call("GET", f"/api/jobs/{jid}/events", status=200).get_data(as_text=True)
    assert "event: done" in body


# --- submit, queue, teacher verify (acceptance steps 7-10) -----------------------------------------
def test_submit_queue_and_teacher_verify_pinned_to_revision(env, app, teacher, ada):
    sid = ada.get("/api/me")["id"]
    save(ada, GOOD)
    assert job(ada, "test")["status"] == "passed"
    entry = ada.post("/api/me/projects/lesson0/submit")
    assert entry["revision"] == 1

    (q,) = teacher.get("/api/teacher/queue")
    assert q["studentName"] == "Ada" and q["revision"] == 1 and q["key"] == f"{sid}_lesson0"

    # Ada breaks her code after submitting: the submission must not change.
    save(ada, STARTER)
    assert job(ada, "build")["revision"] == 2
    assert teacher.get("/api/teacher/queue")[0]["revision"] == 1

    key = q["key"]
    b = teacher.post(f"/api/teacher/queue/{key}/build", status=202)
    bj = teacher.wait_job(b["jobId"])
    assert bj["status"] == "passed" and bj["origin"] == "teacher-verify" and bj["revision"] == 1
    t = teacher.wait_job(teacher.post(f"/api/teacher/queue/{key}/test", status=202)["jobId"])
    assert t["status"] == "passed" and t["revision"] == 1, "tests the pinned revision, not Ada's later edit"
    assert t["tests"][0]["status"] == "passed"
    # teacher jobs never alter Ada's project record
    assert ada.get("/api/me/projects/lesson0")["lastTest"]["revision"] == 1
    teacher.post("/api/teacher/queue/nope_x/build", status=404)

    # Restart: everything is still there.
    app2 = create_app(env)
    t2 = Api(app2)
    t2.login("teach", "secret1")
    assert t2.get("/api/teacher/queue")[0]["revision"] == 1
    a2 = Api(app2)
    a2.login("ada", "pw1234")
    assert a2.get("/api/me/projects/lesson0")["source"] == STARTER

    # Resubmitting replaces the entry.
    save(a2, GOOD)
    assert job(a2, "test")["status"] == "passed"
    a2.post("/api/me/projects/lesson0/submit")
    q = t2.get("/api/teacher/queue")
    assert len(q) == 1 and q[0]["revision"] == 3


def test_teacher_review(teacher, ada):
    sid = ada.get("/api/me")["id"]
    save(ada, GOOD)
    job(ada, "test")
    (s,) = teacher.get("/api/teacher/students")
    assert s["projects"]["lesson0"]["lastTest"]["status"] == "passed" and "passwordHash" not in s
    r = teacher.get(f"/api/teacher/students/{sid}/projects/lesson0")
    assert r["source"] == GOOD and r["lastTestJob"]["status"] == "passed" and r["revisions"] == [1]
    assert teacher.get(f"/api/teacher/students/{sid}/projects/lesson0/revisions/1")["source"] == GOOD
    teacher.get(f"/api/teacher/students/{sid}/projects/lesson0/revisions/9", 404)


def test_running_jobs_are_marked_interrupted_on_restart(env, app, ada):
    save(ada, INFINITE)
    jid = ada.post("/api/me/projects/lesson0/test", status=202)["jobId"]
    ada.wait_running_tests(jid)
    # Simulate a crash: a new server process starts while the old build.json still says "running".
    app2 = create_app(env)
    a2 = Api(app2)
    a2.login("ada", "pw1234")
    j = a2.get(f"/api/jobs/{jid}")
    assert j["status"] == "failed" and j["reason"] == "interrupted"
    ada.post(f"/api/me/jobs/{jid}/stop")
    ada.wait_job(jid, 10)
