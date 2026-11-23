"""Flask application: JSON API, session login with two roles, static React apps."""
import json
import logging
import re
from datetime import timedelta
from functools import wraps
from types import SimpleNamespace

import click
from flask import Flask, Response, abort, g, jsonify, make_response, redirect, request, send_from_directory, session

from .accounts import AccountError, Accounts
from .builder import BuildService
from .config import load_config
from .jobs import JobBusy, JobManager, ServerBusy, load_job_dict
from .lessons import Lessons
from .projects import ProjectError, Projects
from .storage import valid_id

log = logging.getLogger("robotics")

LANDING = """<!doctype html><meta charset="utf-8"><title>Robotics</title>
<body style="font-family:sans-serif;max-width:30em;margin:3em auto">
<h1>Robotics</h1><p><a href="/ide/">Student IDE</a></p><p><a href="/instructor/">Instructor</a></p></body>"""


def create_app(overrides: dict | None = None) -> Flask:
    cfg = load_config(overrides)
    app = Flask(__name__, static_folder=None)
    app.secret_key = cfg.secret_key
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=cfg.session_cookie_secure,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )

    lessons = Lessons(cfg.lessons_dir, cfg.data_dir)
    accounts = Accounts(cfg.data_dir, cfg.password_hash_method)
    projects = Projects(cfg.data_dir, lessons, cfg.max_source_kb)
    service = BuildService(cfg, lessons)
    jobs = JobManager(cfg, service)
    app.robotics = SimpleNamespace(cfg=cfg, lessons=lessons, accounts=accounts, projects=projects,
                                   service=service, jobs=jobs)

    # --- helpers ---------------------------------------------------------
    def err(msg: str, status: int):
        return jsonify({"error": msg}), status

    def abort_json(msg: str, status: int):
        abort(make_response(jsonify({"error": msg}), status))

    def body() -> dict:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort_json("Expected a JSON object in the request body.", 400)
        return data

    @app.errorhandler(404)
    def _404(_e):
        return err("Not found.", 404)

    @app.errorhandler(405)
    def _405(_e):
        return err("Method not allowed.", 405)

    @app.errorhandler(413)
    def _413(_e):
        return err("That request is too large.", 413)

    @app.errorhandler(500)
    def _500(_e):
        return err("Something went wrong inside the server.", 500)

    def current_user():
        """The logged-in account, re-checked on every request (disabled students lose access at once)."""
        role, uid = session.get("role"), session.get("id")
        if role == "instructor":
            t = accounts.instructor()
            if t and t["id"] == uid:
                return "instructor", t
        elif role == "student":
            s = accounts.student(uid)
            if s and s.get("enabled", True):
                return "student", s
        return None

    def require(role: str):
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                u = current_user()
                if not u:
                    return err("Please log in.", 401)
                if u[0] != role:
                    return err("You don't have access to that.", 403)
                g.role, g.user = u
                return fn(*a, **kw)
            return wrapper
        return deco

    def require_any(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                return err("Please log in.", 401)
            g.role, g.user = u
            return fn(*a, **kw)
        return wrapper

    def lesson_or_404(lid: str):
        """A student's view: only enabled lessons exist."""
        meta = lessons.meta(lid)
        if not meta or not lessons.is_enabled(lid):
            abort_json("No such lesson.", 404)
        return meta

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # --- session ---------------------------------------------------------
    @app.post("/api/login")
    def login():
        d = body()
        res = accounts.authenticate(str(d.get("username", "")), d.get("password"))
        if not res:
            return err("Wrong username or password.", 401)
        role, rec = res
        session.clear()
        session.permanent = True
        session["role"], session["id"] = role, rec["id"]
        return jsonify({"role": role, "id": rec["id"], "name": rec["name"]})

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/me")
    @require_any
    def me():
        return jsonify({"role": g.role, "id": g.user["id"], "name": g.user["name"]})

    # --- lessons (students see enabled ones only) --------------------------
    @app.get("/api/lessons")
    @require("student")
    def list_lessons():
        return jsonify(lessons.list_enabled())

    # --- student: projects ------------------------------------------------
    def project_view(sid: str, lid: str) -> dict:
        meta = lessons.meta(lid)
        active = jobs.active_for(sid)
        return {**projects.state(sid, lid), "title": meta["title"], "source": projects.read_source(sid, lid),
                "activeJobId": active.id if active else None}

    @app.get("/api/me/projects/<lid>")
    @require("student")
    def open_project(lid):
        lesson_or_404(lid)
        return jsonify(project_view(g.user["id"], lid))

    @app.put("/api/me/projects/<lid>/source")
    @require("student")
    def save_source(lid):
        lesson_or_404(lid)
        try:
            projects.save_source(g.user["id"], lid, body().get("source"))
        except ProjectError as e:
            return err(str(e), 400)
        return jsonify(projects.state(g.user["id"], lid))

    def start_job(kind: str, origin: str, owner: str, sid: str, lid: str, rev: int, path, reuse):
        meta = lessons.meta(lid)

        def run(job):
            service.execute(job, path, meta, reuse)

        try:
            job = jobs.start(kind=kind, origin=origin, owner=owner, student_id=sid, lesson_id=lid, revision=rev,
                             class_name=meta["className"], api_version=meta.get("apiVersion", 0), run=run,
                             on_finish=projects.record_job if origin == "student" else None)
        except JobBusy as e:
            return err(str(e), 409)
        except ServerBusy as e:
            return err(str(e), 503)
        return jsonify({"jobId": job.id, "revision": rev}), 202

    def student_job(kind: str, lid: str):
        lesson_or_404(lid)
        sid = g.user["id"]
        if jobs.active_for(sid):
            return err("You already have a build or test running. Wait for it to finish, or press Stop.", 409)
        rev, path = projects.snapshot(sid, lid)  # the job compiles this snapshot, never the working copy
        reuse = projects.good_build(sid, lid, rev) if kind == "test" else None
        return start_job(kind, "student", sid, sid, lid, rev, path, reuse)

    @app.post("/api/me/projects/<lid>/build")
    @require("student")
    def student_build(lid):
        return student_job("build", lid)

    @app.post("/api/me/projects/<lid>/test")
    @require("student")
    def student_test(lid):
        return student_job("test", lid)

    @app.post("/api/me/projects/<lid>/submit")
    @require("student")
    def student_submit(lid):
        lesson_or_404(lid)
        try:
            entry = projects.submit(g.user["id"], lid)
        except ProjectError as e:
            return err(str(e), 409)
        return jsonify(entry)

    @app.post("/api/me/jobs/<jid>/stop")
    @require("student")
    def student_stop(jid):
        job = jobs.get(jid) if valid_id(jid) else None
        if not job or job.owner != g.user["id"]:
            return err("No such job.", 404)
        job.cancel.set()
        return jsonify({"ok": True})

    # --- jobs (owner or instructor) -------------------------------------------
    def job_for(jid: str):
        """(live Job or None, dict) for a job the caller may see; aborts with 404 otherwise."""
        if not valid_id(jid):
            abort_json("No such job.", 404)
        live = jobs.get(jid)
        rec = live.to_dict(include_output=True) if live else load_job_dict(jobs.builds_dir, jid)
        if rec is None or (g.role == "student" and rec["owner"] != g.user["id"]):
            abort_json("No such job.", 404)
        return live, rec

    @app.get("/api/jobs/<jid>")
    @require_any
    def get_job(jid):
        return jsonify(job_for(jid)[1])

    @app.get("/api/jobs/<jid>/events")
    @require_any
    def job_events(jid):
        live, rec = job_for(jid)
        try:
            after = int(request.headers.get("Last-Event-ID") or request.args.get("after") or 0)
        except ValueError:
            after = 0

        def fmt(e):
            return f"id: {e['id']}\nevent: {e['type']}\ndata: {json.dumps(e)}\n\n"

        def gen():
            if live is None:  # finished before a restart: replay what was saved
                if rec.get("output"):
                    yield fmt({"id": 1, "type": "output", "text": rec["output"]})
                yield fmt({"id": 2, "type": "done", "text": "", "job": rec})
                return
            idx = after
            while True:
                evs, finished = live.wait_events(idx, 15)
                if not evs and not finished:
                    yield ": keepalive\n\n"
                    continue
                for e in evs:
                    idx = e["id"]
                    yield fmt(e)
                    if e["type"] == "done":
                        return

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    # --- instructor: students -------------------------------------------------
    @app.post("/api/instructor/students")
    @require("instructor")
    def create_student():
        d = body()
        try:
            rec = accounts.create_student(d.get("name"), d.get("username"), d.get("password"))
        except AccountError as e:
            return err(str(e), 400)
        return jsonify(accounts.public(rec)), 201

    @app.get("/api/instructor/students")
    @require("instructor")
    def list_students():
        out = []
        for s in accounts.students():
            out.append({**accounts.public(s), "projects": projects.student_summaries(s["id"])})
        return jsonify(out)

    @app.patch("/api/instructor/students/<sid>")
    @require("instructor")
    def patch_student(sid):
        d = body()
        try:
            rec = accounts.update_student(sid, enabled=d.get("enabled"), password=d.get("password"),
                                          name=d.get("name"))
        except KeyError:
            return err("No such student.", 404)
        except AccountError as e:
            return err(str(e), 400)
        return jsonify(accounts.public(rec))

    # --- instructor: lessons (defined in the repo; the instructor only enables/disables) ---
    @app.get("/api/instructor/lessons")
    @require("instructor")
    def instructor_lessons():
        return jsonify(lessons.list_with_state())

    @app.patch("/api/instructor/lessons/<lid>")
    @require("instructor")
    def patch_lesson(lid):
        enabled = body().get("enabled")
        if not isinstance(enabled, bool):
            return err("Send {\"enabled\": true} or {\"enabled\": false}.", 400)
        try:
            lessons.set_enabled(lid, enabled)
        except KeyError:
            return err("No such lesson.", 404)
        return jsonify(next(m for m in lessons.list_with_state() if m["id"] == lid))

    # --- instructor: review, queue, verify --------------------------------------
    def job_summary(ref):
        if not ref:
            return None
        rec = load_job_dict(jobs.builds_dir, ref["jobId"], include_output=False)
        return rec

    @app.get("/api/instructor/students/<sid>/projects/<lid>")
    @require("instructor")
    def review_project(sid, lid):
        student = accounts.student(sid)
        meta = lessons.meta(lid)
        if not student or not meta or not projects.exists(sid, lid):
            return err("No such project.", 404)
        st = projects.state(sid, lid)
        return jsonify({**st, "student": accounts.public(student), "title": meta["title"],
                        "source": projects.read_source(sid, lid), "revisions": projects.revisions(sid, lid),
                        "lastBuildJob": job_summary(st["lastBuild"]), "lastTestJob": job_summary(st["lastTest"])})

    @app.get("/api/instructor/students/<sid>/projects/<lid>/revisions/<int:rev>")
    @require("instructor")
    def review_revision(sid, lid, rev):
        meta = lessons.meta(lid)
        if not valid_id(sid) or not meta or rev not in projects.revisions(sid, lid):
            return err("No such revision.", 404)
        p = projects.revision_path(sid, lid, meta["className"], rev)
        return jsonify({"revision": rev, "source": p.read_text("utf-8", "replace")})

    @app.get("/api/instructor/queue")
    @require("instructor")
    def instructor_queue():
        out = []
        for e in projects.queue():
            s = accounts.student(e["studentId"]) or {}
            m = lessons.meta(e["lessonId"]) or {}
            out.append({**e, "studentName": s.get("name", "?"), "studentLogin": s.get("login", "?"),
                        "lessonTitle": m.get("title", e["lessonId"])})
        return jsonify(out)

    def verify(kind: str, key: str):
        e = projects.queue_entry(key)
        if not e:
            return err("No such submission.", 404)
        meta = lessons.meta(e["lessonId"])
        if not meta:
            return err("The lesson of this submission no longer exists.", 404)
        sid, lid, rev = e["studentId"], e["lessonId"], e["revision"]
        # Pinned to the submitted revision snapshot, not the student's live workspace.
        path = projects.revision_path(sid, lid, meta["className"], rev)
        if not path.exists():
            return err("The submitted revision is missing.", 404)
        reuse = projects.good_build(sid, lid, rev) if kind == "test" else None
        return start_job(kind, "instructor-verify", "instructor", sid, lid, rev, path, reuse)

    @app.post("/api/instructor/queue/<key>/build")
    @require("instructor")
    def verify_build(key):
        return verify("build", key)

    @app.post("/api/instructor/queue/<key>/test")
    @require("instructor")
    def verify_test(key):
        return verify("test", key)

    @app.post("/api/instructor/jobs/<jid>/stop")
    @require("instructor")
    def instructor_stop(jid):
        job = jobs.get(jid) if valid_id(jid) else None
        if not job or job.owner != "instructor":
            return err("No such job.", 404)
        job.cancel.set()
        return jsonify({"ok": True})

    # --- static React apps ------------------------------------------------
    @app.get("/")
    def landing():
        return Response(LANDING, mimetype="text/html")

    def static_app(name: str, root):
        def index():
            if root is None:
                return Response(f"The {name} app is not built on this server.", status=404, mimetype="text/plain")
            resp = send_from_directory(root, "index.html")
            resp.headers["Cache-Control"] = "no-cache"
            return resp

        def asset(path):
            if root is None or not re.match(r"^[A-Za-z0-9._/-]+$", path) or ".." in path:
                abort(404)
            return send_from_directory(root, path)

        app.add_url_rule(f"/{name}", f"{name}_redir", lambda: redirect(f"/{name}/"))
        app.add_url_rule(f"/{name}/", f"{name}_index", index)
        app.add_url_rule(f"/{name}/<path:path>", f"{name}_asset", asset)

    static_app("ide", cfg.web_ide)
    static_app("instructor", cfg.web_instructor)

    # --- CLI -----------------------------------------------------------------
    @app.cli.command("bootstrap-instructor")
    @click.argument("username")
    @click.option("--force", is_flag=True, help="Replace the existing instructor account.")
    def bootstrap_instructor(username, force):
        """Create the instructor account. Prompts for a password (or reads ROBOTICS_INSTRUCTOR_PASSWORD)."""
        import os
        pw = os.environ.get("ROBOTICS_INSTRUCTOR_PASSWORD") or click.prompt(
            "Instructor password", hide_input=True, confirmation_prompt=True)
        try:
            accounts.create_instructor(username, pw, force=force)
        except AccountError as e:
            raise click.ClickException(str(e))
        click.echo(f"Instructor account '{username}' created.")

    return app
