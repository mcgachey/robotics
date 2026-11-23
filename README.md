# robotics

Phase 0: a classroom server on a Raspberry Pi where students write Java in a browser, build and test it, and submit.
Plans: `docs/plans/phase_0/` (`plan.md`, `build_server.md`).

## Layout

| Path | What |
|------|------|
| `api/` | `robotics-api.jar` (Program, Robot, MockRobot, ProgramRunner) and the JUnit harness (Java 8 target) |
| `server/` | Flask app: accounts, lessons, projects, build/test jobs, submit queue |
| `web/` | npm workspaces: `common`, `ide` (student, Monaco), `instructor` |
| `lessons/lesson0/` | Hello World lesson: `lesson.json`, `starter/`, `tests/` |
| `scripts/` | `deploy`, `self-check`, `acceptance-test` |
| `deps/astromech.env` | Pinned `astromech_server` commit; `scripts/controller-build` fetches it and builds the ESP32 board controller (UI on port 5050, service `robotics-controller`) |
| `bin/` | `init_rp.sh`, `update_rp.sh` (Pi provisioning) |

## Develop on a laptop

Needs JDK 11+ (with `--release 8`), Python 3, Node 22.

```bash
make deps build test PREFIX=$PWD/.local     # downloads JUnit, builds jars, venv, web; runs all tests
scripts/acceptance-test                     # end-to-end check against a throw-away server
```

Run the server by hand (data in `data-dev/`), then open <http://127.0.0.1:5000/ide/> or `/instructor/`:

```bash
ROBOTICS_INSTRUCTOR_PASSWORD=pw .local/venv/bin/flask --app server.app bootstrap-instructor instructor   # once
make run PREFIX=$PWD/.local
```

Create students and lessons in the instructor page (Lesson 0 can be pasted from `lessons/lesson0`).
Web dev server with hot reload: `cd web/ide && npx vite` (proxies `/api` to port 5000).

## Running student code on a droid

The instructor page's **Hardware** tab lists the droid boards the Pi's board controller (`CONTROLLER_URL`, default
`http://127.0.0.1:5050`) knows about. Each droid has zero or one assigned program: pick a student, pick one of their
built revisions (latest first), press **Deploy**. The server runs that build in its own JVM (`robotics.DeployRunner`,
at most `DEPLOY_MAX_SEC`, default 600 s) whose `DroidRobot` drives that one board through the controller's loopback-only
`motor` / `rotate_head` / `stop` commands. **Stop** kills the run, and a stop is always sent to the droid afterwards.
Output streams to the tab like a build's. Any successful build of a revision (the student's or the instructor's) can be
deployed. This needs the droid firmware and controller from astromech_server with the `motor` and `rotate_head`
commands; bump `deps/astromech.env` to a commit that has them and reflash the boards.

## On the Pi

`sudo bin/init_rp.sh [branch]` once, then `sudo bin/update_rp.sh [branch]` to update.
See `docs/plans/phase_0/build_server.md`.
