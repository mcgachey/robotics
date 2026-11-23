# Architecture: Java Robotics for Middle Schoolers

Status: draft. `TODO` marks open items.

## 1. Overview

Teach middle schoolers Java through robotics, in two phases:

1. **Phase 1**: Droid Depot toy droids (Disney), controlled over Bluetooth LE through an ESP32 running our firmware.
2. **Phase 2**: an actual FTC robot, using the same student-facing Java API.

Students write Java in a browser IDE on Chromebooks. A Raspberry Pi 4 hosts everything else. Students build and test their own code independently; the **teacher** decides when code runs on shared hardware.

### Constraints and principles

- **Two lifecycle modes** (see "Pi lifecycle" below). The Pi has internet at **config time** and none at **classroom time**. Nothing may depend on the internet at classroom time, so all tooling is local then.
- Everything student-facing runs in a browser.
- **Java 8 for everything students touch.** The FTC SDK compiles at Java 8 (`build.common.gradle`), so the student API, mocks, student builds, and lesson tests are all pinned to Java 8 (`javac --release 8` on a newer JDK is fine). This does not apply to the server and UI, which use the stack below.
- **Simplicity over hardening.** Students are 11 years old, not adversaries. Isolation exists to survive accidents (infinite loops, runaway output, crashes), not to resist malicious code.
- Hardware is shared and limited. Many students work at once without needing a robot each.
- Same student-facing API in both phases. The runtime and packaging may differ.

Curriculum and learning outcomes are out of scope for this document.

### Pi lifecycle: config time and classroom time

The Pi runs in one of two modes. This split is core to the architecture, and every Pi-related decision should say which mode it belongs to.

| | **Config time** | **Classroom time** |
|---|---|---|
| Internet | Available (Pi connected to a normal network) | None. The Pi is on the offline classroom router only |
| Who | Teacher or admin, at a desk, before or between classes | Students and teacher, during class |
| Purpose | Pull the code, install and update the OS packages and toolchains, **build** the server and UIs on the Pi, deploy, and verify the install | Serve the IDE and teacher apps, build, test, queue, and (Phase 1) run programs |
| Allowed | Package installs, downloads, `apt`, updates, backups pushed off-box | Only what is already on the Pi. No downloads, no package installs, no external calls |
| Students | Not using the system | Use it |

Rules:

- **Everything classroom time needs is installed at config time.** Configuration ends with a self-check that proves the Pi works with the network unplugged (for example, run the acceptance test offline).
- **The classroom-time software never makes outbound requests.** No CDNs, telemetry, update checks, or DNS-dependent features. If it would work only online, it belongs in config time.
- **Switching modes is a physical, deliberate act**: move the Pi between networks (or enable and disable its uplink). The server does not need to detect the mode. Mode-dependent behaviour is limited to operational tasks (installing, updating) that are performed by a person.
- **Updates are config-time only.** Code arrives by `git pull` from the GitHub repo. Dependencies are pinned and recorded (lockfiles, versions, checksums), so a config run is repeatable and a spare Pi can be rebuilt the same way.
- **The Pi builds its own software.** There is no prebuilt release bundle. Config time installs the build tools (compilers, Python, Node) on the Pi, and Makefiles compile and deploy everything there.
- **Student data survives mode changes.** Config-time work (updates, reinstalls) must not delete workspaces; take a backup first.

TODO: how the Pi is connected for config (separate Ethernet uplink vs. temporarily joining another WiFi).

### Implementation stack and delivery

| Part | Technology |
|------|------------|
| Server components (web/API server, build service, hardware queue, coordinator) | **Python 3 with Flask** |
| Student IDE and teacher interface | **React with Mantine** (TypeScript, built with Vite), served by the Flask server as static files |
| Student API, mocks, lesson tests, and student-code builds | **Java 8** (`javac --release 8` on the Pi's JDK, JUnit 4) |
| Phase 1 runtime (IoC) | TBD. It must load a student JAR, so it runs on a JVM and is launched by the Python server |
| Build and deploy pipelines | **Makefiles** in the repo |
| Provisioning and updates | Two scripts in the repo's `bin/` directory: `init_rp.sh` and `update_rp.sh` |

Delivery model:

1. **The repo on GitHub is the single source.** The Pi gets code only through `git pull` at config time.
2. **Two scripts in `bin/`**, each taking an optional branch name (default `main`). `init_rp.sh` holds all the one-time configuration and takes a bare Raspberry Pi OS install to a provisioned server: system packages, JDK, Python environment, Node toolchain, user and directories, service installation, and a first build and deploy. It is idempotent. `update_rp.sh` is the routine update: it assumes `init_rp.sh` has already run with the same branch, pulls that branch, then builds, deploys, and checks.
3. **Makefiles own the pipelines.** A root Makefile drives per-component Makefiles. There are two pipelines: **compile** (`make build`: Python environment, React bundle, Java API jar) and **deploy** (`make deploy`: install the build output into the single venv and app directory, restart the service, run checks). The `bin/` scripts call the same targets an engineer would run by hand.
4. **Build tools live on the Pi** (Python and venv, Node and npm, JDK, `make`, `git`). They are installed at config time and stay installed. The only classroom-time restriction is that there is no internet, so a build that must download something (`pip install`, `npm ci`, `git pull`) can run only at config time, or from dependencies already cached on the Pi. Nothing in the running system needs the network.

Details for the first phase are in `plans/phase_0/build_server.md`.

### Open items
- TODO: class size, and number of droids and FTC robots
- TODO: target build/test latency

## 2. System Overview

```text
 Student Chromebooks          Teacher Chromebook
   (IDE: edit/build/test/      (review, build/test,
         submit)                assign hardware, run)
          \                        /
           +--------- WiFi --------+
                      |
              Offline WiFi router
                      |
 +--------------------------------------------+
 | Raspberry Pi 4                              |
 |  IDE and teacher web apps                   |
 |  Accounts, lessons, workspaces              |
 |  Build/test service                         |
 |  Hardware queue and deployment coordinator  |
 |  Phase 1 runtime (IoC)                      |
 +--------------------------------------------+
        |                          |
   Phase 1                      Phase 2
   ESP32 BLE bridge             FTC build/deploy
        | BLE                       |
   Droid Depot droid            FTC robot
```

TODO: Pi-to-ESP32 transport, and the deployment path to the FTC robot.

## 3. Phases

**Phase 1: toy droids.** Student code runs on the Pi inside a central runtime that owns `main()` (inversion of control). The student writes a class implementing a robotics interface. The runtime provides the API and forwards commands to the assigned droid via the ESP32.

**Phase 2: FTC robot.** Student code runs on the FTC robot using the FTC SDK. A separate FTC-specific build and deploy implementation sits behind the common pipeline. It does not use the Phase 1 runtime.

**Shared:** IDE, accounts, lessons and workspaces, build/test workflow, hardware queue, teacher interface, and the student-facing API.

## 4. Network

- **Classroom time**: offline WiFi router; Chromebooks (student and teacher) and the Pi join it.
- **Config time**: the Pi is connected to a network with internet instead (see "Pi lifecycle"). Chromebooks are not involved.
- The Pi serves all web apps and assets (no CDNs), and needs no external services at classroom time.
- TODO: SSID/security and Chromebook provisioning
- TODO: Pi addressing and local hostname
- TODO: wired vs. WiFi for the Pi
- TODO: client isolation and capacity
- TODO: Chromebook behavior with no internet (captive-portal checks)

## 5. Raspberry Pi 4

Hosts: the student IDE and teacher interface, accounts and workspaces, the build/test service, the hardware queue and deployment coordinator, and the Phase 1 runtime. Stores source, artifacts, and logs.

Lifecycle: provisioning, installs, builds, and updates happen at **config time** (internet available). Everything above runs at **classroom time** with no internet (see "Pi lifecycle"). Provisioning is done by `bin/init_rp.sh` on a bare Raspberry Pi OS install, and updates by `bin/update_rp.sh` (see "Implementation stack and delivery").

Build tools installed on the Pi: Python 3 and `venv`, Node and npm, a JDK, `make`, and `git`.

- TODO: reset procedure (re-image, then re-run `init_rp.sh`)
- TODO: version pinning policy for OS packages, and the offline self-check contents
- TODO: resource budget (builds vs. Phase 1 runtime), concurrency limits
- TODO: storage medium (SSD preferred over SD), backups, quotas
- TODO: recovery if the Pi fails (spare Pi or re-image plan)

## 6. Student IDE

A minimal browser IDE (React and Mantine, with Monaco bundled locally) with one source file per project.

- Java syntax highlighting and indentation.
- Auto-save to the student's workspace.
- Choose a lesson to open its project (section 8).
- Buttons:
  - **Build**: compile only, report diagnostics.
  - **Test**: compile (if needed), then run the lesson's tests against the mock robotics API.
  - **Submit**: add the current successful build to the hardware queue (section 7).
  - **Stop**: cancel a running build or test.
- An output terminal below the editor streams results: status, compiler diagnostics, test results, and program output. Diagnostics also appear inline in the editor and link to their line. Messages are beginner-friendly, and raw output is available.
- While a build or test is running, the student cannot start another.
- The IDE never touches hardware.

TODO: what Submit requires (successful Build, or passing Test).

## 7. Teacher Interface

A browser app (React and Mantine) on the Pi, requiring a teacher login.

- **Accounts**: create students, reset credentials, enable/disable.
- **Lessons**: define lessons (starter code, tests, target phase).
- **Review**: view students, their projects, source, and build/test status.
- **Build and Test buttons**: run the same pipeline on a student's submitted code to check it before it goes on hardware.
- **Hardware queue**: see submissions in order, with the student, lesson, and source revision.
- **Hardware assignment**: assign a droid or FTC robot to a queued submission, and release it.
- **Run control**: start and stop a program, and view status and logs.
- **Backup**: export and restore workspaces.

Students cannot reach any of these functions.

## 8. Lessons and Workspaces

- A **lesson** defines: starter code, tests, the target phase, and the API version.
- A student has one **project** per lesson, created from the lesson's starter on first use. A student can switch between projects and return to earlier work.
- Each student has a unique ID and their own workspace of projects. Access is enforced server-side.
- Work persists across browser restarts, Chromebook disconnections, and Pi reboots, and writes are safe against interruption.
- Resetting a project to its starter requires confirmation.
- Updating a lesson's starter does not overwrite existing student projects.
- Source is kept in a simple, predictable filesystem layout; avoid a database server unless needed.

## 9. Student API and Runtime

The student sees one Java API in both phases. Implementations differ behind it.

- **Java 8 compatible.** The API library must run on FTC's Android environment as well as the Pi.
- **Versioned.** Artifacts record the API version they were built against.
- **Phase 1**: the central runtime on the Pi loads the student's minimal JAR, supplies the API, and routes commands to the assigned droid. Student code does not define `main()`. Student code runs in its own JVM process with a timeout and resource limits, so a runaway program can be stopped and doesn't take down the Pi.
- **Phase 2**: the FTC implementation provides the API within the FTC SDK's program structure.
- **Mock implementation**: used by Test, so no hardware is needed.

Related existing projects: `/workspace/libastromech`, `/workspace/astromech_server`.

- TODO: define the API surface
- TODO: define the Phase 1 student class contract
- TODO: define how the API maps onto the FTC programming model
- TODO: API compatibility rules between runtime and student artifacts

## 10. ESP32 BLE Bridge

Runs on an ESP32, speaks BLE to Droid Depot droids, and gives the Phase 1 runtime a simple interface for controlling them. It does not run student Java.

Related projects: `/workspace/droid`, `/workspace/libastromech`.

- TODO: Pi-to-ESP32 transport and protocol
- TODO: number of ESP32s, and the pairing and droid-assignment workflow
- TODO: firmware update procedure

## 11. Robot Hardware

- **Droid Depot droids**: Phase 1 targets, controlled through the ESP32 bridge.
- **FTC robot**: Phase 2 target; FTC SDK is in `/workspace/robotics/FtcRobotController`.
- TODO: supported models and hardware configurations
- TODO: batteries, charging, spares
- TODO: field and safety requirements

## 12. Build, Test, and Deploy Workflow

One pipeline serves both phases. Phase-specific steps sit behind it, and student builds and deployable artifacts use the same configuration.

```text
STUDENT                                TEACHER

edit and auto-save                     review queue
      |                                     |
Build (compile)  <--------+            Build / Test the submission
      |                    |                |
Test (lesson tests on      |            assign hardware
 mock API)                 |                |
      |                    |            Run (deploy and start)
Submit --> hardware queue -+--------->      |
                                        Stop / status / logs
```

**Build service** (a component of the Flask server)
- Compiles with the local JDK at Java 8, with no internet (classroom time; the JDK was installed at config time). The Python service starts `javac` and JUnit as child processes.
- Test compiles first if needed, then runs the lesson's tests against the mock API.
- Returns structured diagnostics, test results, and program output, streamed to the terminal.
- Runs each test in a separate process with a timeout and memory and output caps, to survive accidents.
- One active build per student; a global limit and a queue protect the Pi.

**Artifacts**
- A successful build produces an artifact tied to the exact source revision, student, lesson, target phase, and API version.
- Editing after a build or submit never changes a submitted artifact.
- A failed build never replaces the last successful artifact.

**Submit and queue**
- Submit adds a student's successful build to the hardware queue, pinned to that revision.
- One queued submission per student per lesson; resubmitting replaces it.
- Only the teacher can take a submission off the queue and run it.

**Deployment**
- The teacher assigns hardware and starts the run. A hardware device runs only one program at a time.
- The coordinator calls the Phase 1 or Phase 2 deployment implementation.
- **Phase 1**: load the student JAR into the Pi runtime and run it against the assigned droid.
- **Phase 2**: build for FTC and deploy to the robot.
- Status and logs return to the teacher interface. Deployment history is recorded.

TODO: Phase 2 build toolchain and where it runs, offline dependencies, deployment mechanism, log retrieval.
TODO: warm compiler vs. fresh `javac` per build, based on Pi latency.

## 13. Operations and Safety

- **Roles**: student and teacher, enforced server-side. Only teachers assign hardware and run programs.
- **Hardware safety**: the teacher can always stop a program. A program stops on timeout or if its connection drops. A physical power-off or emergency-stop procedure must be available.
- **Logging**: logins, administrative actions, deployments, and build errors.
- **Maintenance**: all updates (Pi OS, toolchains, libraries, our own code via `git pull` and `make deploy`, firmware tooling) are done at config time, never during class. The Pi is disposable: it tracks one branch of the repo, deploys replace the installed app in place, and there is no versioning, rollback, or repair. A bad Pi is re-imaged and re-provisioned with `init_rp.sh`. Setup, teardown, and troubleshooting guides; backup and restore (back up before any config-time change).
- TODO: emergency-stop requirements
- TODO: hardware release policy and per-run time limits
- TODO: teacher login bootstrap and credential policy

## 14. Next Steps

**Feasibility spikes first**
1. FTC build and deploy from the Pi at classroom time (offline), with its toolchain and dependencies fetched at config time.
2. Pi throughput for concurrent builds and tests alongside the Phase 1 runtime.
3. Pi-to-ESP32-to-droid control loop.

**Milestones**
1. Student loop: edit, Build, Test, with terminal feedback.
2. Phase 1 hardware: a submitted JAR runs on a droid through the runtime.
3. Teacher workflow: accounts, lessons, queue, Build/Test, assign, run, stop.
4. Phase 2: FTC build and deploy.
5. Classroom integration: multiple students, persistence, recovery.
