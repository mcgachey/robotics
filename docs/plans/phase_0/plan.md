# Phase 0 Plan: Hello World, End to End

Status: decisions D1-D6 accepted. Builds on `../../architecture.md` (section numbers below refer to it). Pi setup is in `build_server.md`.

**Lifecycle.** Phase 0 follows the architecture's split of the Pi into **config time** (internet available: pull, build, deploy, verify) and **classroom time** (no internet: run). Everything in this plan runs at classroom time. Everything it needs is installed and built on the Pi at config time, from code pulled with git.

**Stack.** Python 3 and Flask for the server, React and Mantine for the UIs, Java 8 for the student API and student code. Makefiles run the compile and deploy pipelines, and two scripts in `bin/` (`init_rp.sh` for one-time provisioning of a bare Raspberry Pi OS install, `update_rp.sh` for routine updates) take an optional branch name, defaulting to `main`. See `build_server.md` for the procedures.

## 1. Goal

Prove the software loop works before any robot is involved:

1. A teacher creates a student account and defines **Lesson 0**.
2. The student logs in, opens Lesson 0 in the browser IDE, writes a hello world class, then **Builds**, **Tests**, and **Submits** it.
3. The teacher sees the submission in the queue, runs **Build** and **Test** on it with the same backend, and confirms it passes.

This is milestone 1 (student loop) plus a thin slice of milestone 3 (teacher workflow) from section 14. The pipeline's shape is the real one, so later phases extend it rather than replace it.

### Out of scope

- Robotics code: no droid, ESP32, BLE, FTC, or Phase 1 runtime.
- Deploy: no hardware assignment, Run, Stop, or deployment history. The queue is a list, and the teacher can only inspect and Build/Test from it.
- Hardening: no HTTPS, password policy, backup/restore UI, quotas, or global build queue. Students are not adversaries (section 1), but processes still get timeouts and output caps.
- Classroom network provisioning (router, SSIDs), Pi image, and recovery. Develop and demo on a laptop or the Pi with `localhost`. The config-time install procedure itself is in scope (`build_server.md`).

## 2. Decisions

All six recommendations were accepted. **D1 was then superseded**: the server is Python and Flask, not Java (see the D1 row). These shape everything else. The Pi dependencies that follow from them are in `build_server.md`.

| # | Question | Decision |
|---|----------|----------|
| D1 | Server and UI stack | **Python 3 with Flask for the server; React with Mantine (TypeScript, Vite) for the IDE and teacher UIs. Java 8 only for the student API, mocks, and the student-code toolchain.** *(Supersedes the earlier "Java server" recommendation.)* The server shells out to `javac` and JUnit as child processes. The Pi builds everything itself at config time, with `make`, from code pulled with git. |
| D2 | Lesson test framework | **JUnit 4 jars**, downloaded at config time with pinned checksums (Java 8 compatible, not fetched at classroom time). Lesson tests are ordinary `.java` files, so a teacher can author them. |
| D3 | What Submit requires (open TODO, section 6) | **A passing Test of the exact current source revision.** Build-only is too weak for a gate, and Phase 0 has one cheap test to check. |
| D4 | Persistence | **Plain files under a data directory, with JSON metadata** (section 8: no database server). |
| D5 | Auth for Phase 0 | **Session cookie, with passwords stored hashed.** Flask's signed session cookie (secret key generated at config time, kept outside git) and `werkzeug.security` password hashes. The teacher is bootstrapped from a CLI command. |
| D6 | Build isolation | **Separate child process per compile and per test run** (each a JVM), with wall-clock timeout, `-Xmx`, and an output cap. Started from Python in its own process group so Stop can kill the whole tree. No containers. |

## 3. Student-facing API for Lesson 0

Section 9 leaves the API surface as a TODO. Phase 0 needs only the smallest piece that proves the contract. Keep it deliberately tiny and mark it `apiVersion = 0`.

Module `robotics-api` (Java 8, no dependencies):

```java
package robotics;

public interface Program {          // the Phase 1 "student class contract" in miniature
    void run(Robot robot) throws Exception;
}

public interface Robot {
    void log(String message);       // hello world output goes here
}
```

- **Student code**: one class implementing `Program`. It does not define `main()`.
- **Mock** (`MockRobot`): records `log` calls in a list. Used by Test.
- **Runner** (`ProgramRunner`): the harness's `main()`. It loads the student class, instantiates it, and calls `run` with a `Robot`. Test uses `MockRobot`. A later phase swaps in the real runtime.

Lesson 0 starter:

```java
import robotics.*;

public class HelloWorld implements Program {
    @Override
    public void run(Robot robot) {
        // TODO: log "Hello, world!"
    }
}
```

Lesson 0 test (JUnit 4):

```java
public class HelloWorldTest {
    @Test public void logsHello() throws Exception {
        MockRobot robot = new MockRobot();
        new HelloWorld().run(robot);
        assertTrue(robot.messages().contains("Hello, world!"));
    }
}
```

The test references `HelloWorld` by name, so the lesson fixes the class name. Lesson metadata records it (section 4.3).

## 4. Components

### 4.1 Server skeleton

One Flask application serving the built React apps as static files and a JSON HTTP API. In production it runs under `gunicorn` as a single worker with threads (job state is shared in memory, and the Pi has little RAM), managed by `systemd`.

- Serves the IDE and teacher apps (React and Mantine, built at config time) as static assets. Monaco comes from the `monaco-editor` npm package and is bundled by Vite, and the editor wrapper is configured to use that local copy so it never loads from a CDN (no outbound requests at classroom time).
- Session login. Two roles: `student` and `teacher`. Role checks are done server-side on every route (sections 7 and 13).
- Every student route is scoped to the logged-in student's ID, and the ID is never taken from the request body.
- Config: data directory, port, build limits (`timeoutSec`, `maxHeapMb`, `maxOutputKb`).

### 4.2 Storage layout

```text
data/
  teacher.json                      # bootstrapped teacher account
  students/<studentId>/student.json # name, login, password hash, enabled
  lessons/<lessonId>/
    lesson.json                     # title, className, targetPhase, apiVersion
    starter/HelloWorld.java
    tests/HelloWorldTest.java
  workspaces/<studentId>/<lessonId>/
    project.json                    # current revision number, last build/test/submit refs
    src/HelloWorld.java             # working copy, auto-saved
    revisions/<n>/HelloWorld.java   # immutable snapshot per build
  builds/<buildId>/
    build.json                      # student, lesson, revision, kind, status, apiVersion, times
    classes/ or artifact.jar        # only on success
    output.log                      # diagnostics, test results, program output
  queue/<studentId>_<lessonId>.json # submission pointing at a buildId
```

Rules from sections 8 and 12 that Phase 0 must already honor:

- **Atomic writes**: write to a temp file, then rename. Auto-save and metadata updates are safe against interruption.
- **Snapshots**: each Build snapshots the source into `revisions/<n>`. The build compiles the snapshot, never the working copy, so edits during a build change nothing.
- **Artifacts are immutable**, and a failed build never replaces the last successful artifact.
- **Starter is a copy**: the project is created from the lesson starter on first open. Later starter edits do not touch existing projects.

### 4.3 Lessons

- `lesson.json`: `id`, `title`, `className`, `targetPhase` (`1` for now, unused), `apiVersion`.
- Phase 0 creates Lesson 0 through the teacher UI (section 4.7). A seed script may preload the same files for tests and demos.

### 4.4 Build service

The core deliverable. The student IDE and teacher UI both call it.

**Build**
1. Snapshot the source revision.
2. Run `javac --release 8` in a child process (Python `subprocess`) against `robotics-api.jar`, writing to `builds/<id>/classes`.
3. Parse diagnostics into structured records: `{file, line, column, severity, message}`, with a beginner-friendly message and the raw text kept alongside.
4. On success, package `artifact.jar` and record `apiVersion`.

**Test**
1. Build first if there is no successful build for this exact revision. Reuse it otherwise.
2. Compile the lesson tests against the artifact, JUnit, and `robotics-api.jar`.
3. Run JUnit in a child JVM with the timeout, heap, and output caps. Test results are `{name, status, message}` records.
4. Student `System.out` is captured and shown as program output.

**Rules**
- One active job per student. A second request while one runs is rejected with a clear message.
- A global concurrency limit of 1 or 2 is enough for Phase 0 (a counter, no queue).
- Each child runs in its own session (`start_new_session=True`), so **Stop** and timeouts use `os.killpg` to kill the whole process tree, and the job is marked `cancelled`. Heap is capped with `-Xmx`, and output is read through a bounded buffer.
- Jobs run on worker threads inside the Flask process. Job state is also written to `builds/<id>/build.json`, so finished jobs survive a restart. Jobs running during a restart are marked `failed (interrupted)` at startup.
- Timeout and output-cap hits are reported as friendly failures ("your program ran too long"), not server errors.
- Jobs are asynchronous. The API returns a job ID, and output streams via Server-Sent Events (or polling, if SSE is a hassle on the first pass). Finished jobs stay readable from `builds/<id>/`.

### 4.5 Submit and queue

- `POST submit` is accepted only if the student's latest build for the current working revision passed Test (D3). It writes `queue/<student>_<lesson>.json` pointing at that build, so resubmitting replaces it.
- Editing after Submit does not change the submission, because it points at an immutable build.
- Queue entry: `{studentId, lessonId, buildId, revision, submittedAt}`.

### 4.6 Student IDE (section 6, minimal)

A React single-page app using Mantine components (`AppShell`, `Button`, `Tabs`, notifications), in `web/ide`:

- Login screen, then lesson picker (a single entry for now).
- Monaco editor (via `@monaco-editor/react`, using the locally bundled Monaco) with Java highlighting. Auto-save on a debounce, with a visible "saved" indicator.
- Buttons: **Build**, **Test**, **Submit**, **Stop**. Build and Test are disabled while a job runs. Submit is enabled only when D3 is met.
- Output terminal below the editor: status line, diagnostics, test results, program output, with a "show raw output" toggle.
- Diagnostics also shown as editor markers that link to the line.
- Skip for now: reset-to-starter, project switching beyond Lesson 0, rich beginner-friendly message rewriting (basic rewrites for 3 or 4 common errors are enough).

### 4.7 Teacher interface (section 7, minimal)

A React and Mantine single-page app (`web/teacher`, sharing components with the IDE through a `web/common` package) behind teacher login:

- **Students**: create a student (name, username, initial password), list, enable/disable. Credential reset is optional.
- **Lessons**: create/edit a lesson (title, class name, starter code, test code) using plain text areas.
- **Review**: list students and their Lesson 0 project, with the source and the latest build/test status.
- **Queue**: list submissions in order, with student, lesson, and revision.
- **Build / Test buttons** on a queue entry: run the same build service against that submission's pinned revision. This is the key requirement for the teacher. It runs the same code path with `kind=teacher-verify`, reads from `revisions/<n>` rather than the live workspace, and shows the same terminal output.

Not in Phase 0: assign hardware, Run, Stop program, remove from queue, backup.

### 4.8 Bootstrap and tooling

- `make bootstrap-teacher USER=<name>` (a Flask CLI command underneath) creates the first teacher. The password policy is a TODO from section 13, and Phase 0 only needs something that works.
- `make seed-lesson0` loads the files from section 3 into `data/lessons/`.
- `junit-4.x.jar` and `hamcrest-core-1.3.jar`, downloaded by `make` at config time and checksum-verified (pinned in `deps/checksums.txt`).
- `bin/init_rp.sh [branch]` (config time) provisions a bare Raspberry Pi OS install: all one-time configuration, then a first `update_rp.sh`. It is idempotent and never touches `data/`.
- `bin/update_rp.sh [branch]` (config time) assumes `init_rp.sh` ran with the same branch. It fetches that branch and runs the Makefile pipelines (`deps build test deploy check`).
- Both default the branch to `main`.
- `make run` starts the server for development, and the `systemd` unit starts it with `gunicorn` in production (classroom time).

### 4.9 Repo layout and Makefiles

```text
bin/init_rp.sh [branch]   # one-time, idempotent: bare Raspberry Pi OS -> provisioned server
bin/update_rp.sh [branch] # routine: fetch branch, then make deps build test deploy check
Makefile                  # root: deps, build, test, deploy, check, run, bootstrap-teacher, seed-lesson0
deps/                     # pinned dependency manifest (checksums.txt, node and JDK versions)
api/                      # Java 8: robotics-api, MockRobot, ProgramRunner   (api/Makefile)
server/                   # Python: Flask app, build service, pytest tests     (server/Makefile)
  requirements.txt        # pinned, with hashes
web/                      # React + Mantine + Vite, TypeScript                 (web/Makefile)
  common/  ide/  teacher/ # package-lock.json is committed
lessons/lesson0/          # starter, tests, lesson.json
scripts/                  # acceptance test, self-check
docs/
```

Root Makefile targets:

| Target | Pipeline | What it does |
|--------|----------|--------------|
| `make deps` | compile | Fetch pinned third-party files (JUnit jars) and verify checksums |
| `make build` | compile | `api` (javac to jar), `server` (venv and `pip install` from `requirements.txt`), `web` (`npm ci` then `vite build`) |
| `make test` | compile | `pytest` for the server, Java API tests, web unit tests |
| `make deploy` | deploy | `pip install` into the single venv at `/opt/robotics/venv`, replace `/opt/robotics/app` with the build output, restart the service, and run a smoke check |
| `make check` | verify | Run `scripts/self-check` (section 7 acceptance test against the running server) |

Each component Makefile has its own `build`, `test`, and `clean` targets, so a developer can work on one part. Everything works on a laptop as well as on the Pi.

## 5. API sketch

All JSON. Student routes act on the session's student only.

| Method | Path | Role | Purpose |
|--------|------|------|---------|
| POST | `/api/login`, `/api/logout` | any | session |
| GET | `/api/lessons` | any | list lessons |
| GET | `/api/me/projects/{lesson}` | student | open project (creates from starter on first use) |
| PUT | `/api/me/projects/{lesson}/source` | student | auto-save |
| POST | `/api/me/projects/{lesson}/build` | student | start Build, returns `jobId` |
| POST | `/api/me/projects/{lesson}/test` | student | start Test, returns `jobId` |
| POST | `/api/me/jobs/{id}/stop` | student | cancel own job |
| POST | `/api/me/projects/{lesson}/submit` | student | enqueue the passing build |
| GET | `/api/jobs/{id}` and `/api/jobs/{id}/events` | owner or teacher | status and streamed output |
| POST/GET | `/api/teacher/students` | teacher | create, list |
| PATCH | `/api/teacher/students/{id}` | teacher | enable/disable |
| POST/PUT/GET | `/api/teacher/lessons[/{id}]` | teacher | define lessons |
| GET | `/api/teacher/students/{id}/projects/{lesson}` | teacher | review |
| GET | `/api/teacher/queue` | teacher | list submissions |
| POST | `/api/teacher/queue/{key}/build`, `/test` | teacher | verify a submission |

## 6. Build order

Each step is demoable and testable on its own.

1. **Repo skeleton, Makefiles, and storage**: the layout and targets from section 4.9, a Flask app, config, atomic-write helper, file layout, login with the two roles, and role-check tests.
2. **API library and mock**: `robotics-api` jar, `MockRobot`, `ProgramRunner`, JUnit jars via `make deps`.
3. **Build service on the command line**: given a source dir and a lesson, produce diagnostics, an artifact, and test results. Unit-test it with good source, a compile error, a failing test, an infinite loop, and runaway output. This step carries the most risk, so do it before any UI.
4. **Job layer**: async jobs, one-per-student rule, Stop, streaming output.
5. **Lessons, students, and projects** (API only): create from starter, auto-save, snapshots, immutability.
6. **Submit and queue**, with the D3 gate.
7. **Student IDE**.
8. **Teacher interface**, including Build/Test on a queued submission.
9. **Provisioning**: `bin/init_rp.sh` on a bare Raspberry Pi OS image, then `bin/update_rp.sh`. Start this early and keep it working, because it is the only path the real system is installed by.
10. **End-to-end script and demo run** (section 7), then fix what it exposes.

Steps 3 and 7 are the risky ones: Pi build latency (open item in section 1) and Monaco running with no internet access (nothing loaded from outside the Pi). Measure compile and test time for Lesson 0 on the actual Pi as soon as step 3 works. It sets the target for the TODO on build latency.

## 7. Acceptance test (definition of done)

Run on the Pi in **classroom mode**: configured at config time, then with the uplink disconnected (or a laptop with the same JDK 8-targeting config and the network disabled). Automate it as a script that drives the HTTP API, and walk through it by hand in a browser once. It doubles as the offline self-check at the end of config time (`build_server.md` section 5).

1. Start from an empty data directory. Bootstrap the teacher.
2. Teacher logs in, creates student `ada`, and creates Lesson 0 with the starter and test from section 3.
3. `ada` logs in on a second browser profile (or a Chromebook), opens Lesson 0, and sees the starter.
4. Build with the starter unchanged: succeeds. Test: **fails** with a readable message.
5. Introduce a syntax error, then Build: shows a diagnostic linked to the right line. The previous successful artifact is still intact.
6. Fix the code to log `Hello, world!`, then Build and Test: both pass. The terminal shows the test result.
7. Submit is only enabled after step 6. Submit, and the entry appears in the teacher queue with the right revision.
8. `ada` edits the source after submitting. The queued submission is unchanged.
9. Teacher clicks Build and Test on the queued submission: both pass, with the same output format as the student saw, and the result matches the pinned revision, not `ada`'s later edit.
10. Restart the server (and ideally power-cycle the Pi). All data is still present and the queue is intact.
11. Negative checks: `ada` cannot call any `/api/teacher/*` route, cannot read another student's project or job, and cannot start a second job while one is running. An infinite loop in student code is killed at the timeout, and the server stays responsive.

## 8. Risks and open questions

- **Build latency on the Pi 4**: cold `javac` plus a JUnit JVM could take several seconds. The warm-compiler question (section 12 TODO) is deferred, and Phase 0 measures it.
- **API surface churn**: `Program`/`Robot` is a placeholder. Keep it in its own versioned module so the later real API replaces it without touching the server.
- **Lesson tests name the student class**: fine for Phase 0. If lessons later allow free class names, the harness needs a lookup convention.
- **Teacher login bootstrap** is a section 13 TODO. Phase 0 uses a CLI command, which may become the final answer.
- **Process-tree kill**: Python's `start_new_session` and `os.killpg` handle this on Linux. Check that Stop and timeout leave no orphan JVMs.
- **Flask under load**: one gunicorn worker with threads is simple but limits parallelism. Child JVMs do the heavy work, so it should be enough. Confirm during the Pi measurements.
- **Build on the Pi**: `npm ci` and `vite build` need Node, a few hundred MB of RAM, and a minute or more on a Pi 4. This is config-time cost only, but check that it fits (use swap if needed).
- **Dependency drift**: pinning (lockfiles, hashes, checksums) is what makes a config run repeatable. A config-time run that fetches something unpinned is a bug.

## 9. What Phase 0 leaves for later

- Phase 1 hardware path: the real runtime behind `Robot`, the queue-to-droid assignment, Run/Stop, and deployment history.
- The full student API (replaces the `log`-only placeholder).
- Classroom features: global build queue, quotas, backup/restore, project switching and reset, hardened sessions.
- Phase 2: FTC build and deploy.
