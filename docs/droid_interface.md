# Droid and FTC Robot Interface Comparison

Status: draft. Compares what the Droid Depot droids (R2 and BB units, via the ESP32 `libastromech` firmware) can do with what the FTC robot can do, as input to the common student-facing API (architecture.md, section 9).

## Sources

| Side | Source | Notes |
|------|--------|-------|
| Droids | `/workspace/libastromech/esp32/src` (`Astromech.h`, `R2Unit.h`, `BBUnit.h`, `Beacon.h`, `astromech_protocol.h`, `astromech_types.h`, `astromech_config.h`) | Arduino/NimBLE library. One board connects to one droid; a separate board runs the beacon. |
| FTC robot | `/workspace/robotics/FtcRobotController` (stock FTC SDK app; `TeamCode` is empty) and `/workspace/robotics/BioBuzzStarterbotTeleop.java` | The FTC "interface" is the SDK's `OpMode` and hardware API (`hardwareMap`, `DcMotor`, `CRServo`, `gamepad1`, `telemetry`). The only robot-specific code in the repo is the goBILDA StarterBot teleop, so the FTC column describes that robot plus the SDK facilities it uses. `UtilityTestHardware` shows the other SDK device types. |

Caveat: the FTC SDK jars are not in the repo (the module only holds the app, utilities and Gradle files). SDK capabilities below that the repo's code does not call (servos, sensors, IMU) are taken from the imports in `UtilityTestHardware.java` and are listed as available, not exercised.

## Summary

The two interfaces are different in kind:

- **Droid**: a *command* interface. Each call is a discrete, timed, fire-and-forget BLE write ("move forward for 1000 ms", "play sound 3"). The droid has no sensors and sends nothing back that the library interprets. The caller owns timing.
- **FTC robot**: a *continuous control* interface. An `OpMode` runs `init()`, then `loop()` repeatedly (many times per second). Each pass sets motor power or velocity from the current inputs and reads state back. Stopping is "set power to 0".

Where the two overlap is differential drive, a stop, and a notion of "is the robot ready". Everything else (audio, head, personality, beacons, connection management) is droid-only, and everything involving feedback (encoders, velocity, sensors, gamepad, telemetry) is FTC-only.

## 1. Functionality in common

| Capability | Droid (ESP32 `libastromech`) | FTC robot (StarterBot teleop / SDK) | Notes for a shared API |
|------------|------------------------------|-------------------------------------|------------------------|
| Differential (skid-steer) drive with independent left and right motors | `Motor::Left`, `Motor::Right`; `moveWheels(leftDir, rightDir, ms, leftSpeed, rightSpeed, ramp)` (protected, wrapped by `R2Unit` and `BBUnit`) | `leftDrive`, `rightDrive` `DcMotor`s; `arcadeDrive(forward, rotate)` sets `left = forward + rotate`, `right = forward - rotate` | Same physical model: two sides driven independently. Turning is by speed difference. |
| Drive forward | `moveForward(ms, speed, ramp)` (R2 and BB) | `arcadeDrive(+forward, 0)` | Droid call is timed and self-stopping; FTC runs until power changes. |
| Drive backward | `moveBackward(ms, speed, ramp)` (R2 and BB) | `arcadeDrive(-forward, 0)` | As above. |
| Turn in place (spin) | R2: `spinClockwise` / `spinCounterClockwise` (wheels opposite directions). BB: `turnHeadClockwise` / `turnHeadCounterClockwise` (same wheel mixing, but turns the head) | `arcadeDrive(0, rotate)` | |
| Arc turn (one side slower or stopped) | R2: `turnClockwise` / `turnCounterClockwise` (one wheel stopped), `driftClockwise` / `driftCounterClockwise` (other wheel at half speed) | `arcadeDrive(forward, rotate)` with both non-zero (continuous mix) | FTC arc is continuous. The droid has four fixed arc shapes. |
| Per-motor speed, signed by direction | `Direction` bit plus speed byte `0x00`-`0xff`; droids don't move below about `0x60` | `setPower(-1.0 .. 1.0)`, sign is direction | Needs a normalised scale and a deadband for the droid. |
| Speed ramping / smoothing | `ramp_ms` per motor command (default 300 ms for wheels; 0 for BB head) | Not used in the teleop. The SDK has `RUN_USING_ENCODER` velocity control (PIDF) on `DcMotorEx` | Different mechanisms: droid ramp is a firmware time constant; FTC would be a velocity PID. |
| Stop | `stop(delay_ms)`; moves auto-send two zero-speed stops after their duration | `setPower(0)`; `ZeroPowerBehavior.BRAKE` on drive and intake motors | Droid has no brake/coast choice. |
| Per-robot default tuning | `DroidDefaults` (wheel speed `0xa0`, wheel ramp 300 ms; head speed and ramp differ by droid), generated from `config/droids/*.yml` | Direction flips (`leftDrive` FORWARD, `rightDrive` REVERSE), brake behaviour, PIDF constants, set in `init()` | Both have a one-time setup of motor characteristics. |
| Setup-before-run lifecycle | `initBle()`, construct `R2Unit` / `BBUnit`, `connect()` (double login) | `OpMode.init()` fetches devices from `hardwareMap` and configures them | Both have an "acquire hardware" step before commands. |
| Addressing a specific robot | By MAC address (`"XX:XX:XX:XX:XX:XX"`) | By configured device name strings (`"left_drive"`, ...) in the robot configuration | Different layers: droid selects the robot; FTC selects the device on one robot. |
| Thread-safe use from several tasks | Mutex-serialised sends; `play()` can run concurrently with `lookAround()` | One OpMode thread; `loop()` is single-threaded by design | A shared API needs a stated concurrency model. |
| Stateless-per-call or last-write-wins output | Each command is independent | Output is whatever was last set; the teleop deliberately sets each motor once per loop | |

## 2. Droid functionality missing from the FTC robot

The FTC StarterBot has no equivalent of any of the following.

### 2.1 Audio (both R2 and BB)

| Droid call | Behaviour |
|------------|-----------|
| `setAudioGroup(group)` | Select an audio group (command `0x0f`, sub-command `0x1f`). |
| `playSoundFromCurrentGroup(sound)` | Play clip N from the current group (`0x18`). |
| `setVolume(0..0x1f)` | Set volume (`0x0e`). Not hardware-verified. |
| `play(Sound, wait)` / `play(index, wait)` | Select group and play as one atomic pair. `wait=true` blocks for the clip's `ms` duration without holding the send mutex. |

Supporting data:

- A **personality** (`Personality{name, sounds[], count}`) is a named bank of `Sound{group, sound, ms}` clips. Five are generated from `config/personalities/*.yml`: `first_order_black`, `resistance_blue`, `resistance_orange`, `resistance_red`, `smuggler_blue`. `findPersonality(name)` returns `nullptr` if unknown.
- Sound durations (`ms`) were measured offline and are used only for `wait=true`.

FTC has no audio output in this robot. The SDK has sound facilities, but none are used here.

### 2.2 Head control (R2 only; BB has no independent head)

| Droid call | Behaviour |
|------------|-----------|
| `rotateHead(dir, speed, ramp, delay_after)` | Spin the dome motor (`Motor::Head`). |
| `centerHead(speed, stop_at_center)` | Drive the head to its centre position (command `0x0f`, sub-command `0x01`). The droid finds centre itself. |
| `lookAround(speed, stop_at_center)` | Left 1.5 s, right 1.5 s, then optionally centre. Blocks about 3 s. |

BB turns its head by spinning the body (`turnHeadClockwise` / `turnHeadCounterClockwise`), so on BB this is a wheel motion with head defaults, not a separate motor. The FTC robot has no head or equivalent. The nearest analogue is a servo or positional motor, which the StarterBot does not have.

### 2.3 Wireless link management

| Droid call | Behaviour |
|------------|-----------|
| `connect(timeout_ms)` / `disconnect()` / `isConnected()` | BLE connect with a random address type, notification subscribe, 500 ms wait, then login frame written twice. |
| `ping()` / `checkAlive()` | Ping, and on failure drop and re-establish the connection. Returns availability. |
| `msSinceLastSuccess()` | Time since the last acknowledged command or ping. |
| Send retry | Up to 3 attempts, reconnecting between attempts. |
| `scanForDroids(out, max, scan_ms)` | Scan for devices advertising as `DROID`. Returns address, address type and RSSI. |
| `onNotification(cb, ctx)` | Register a callback for raw notifications from the droid (single global target). |

The FTC robot's connection (Driver Station to Robot Controller) is managed entirely by the SDK and is invisible to the OpMode. A droid can be unavailable at any time (asleep, remote connected, out of range). An FTC robot is either connected or the OpMode does not run.

Droid-specific constraints with no FTC counterpart:

- The droid refuses connections while its stock remote is connected.
- It auto-sleeps after about 5 minutes with no commands or beacon traffic.
- Writes are acknowledged by the BLE stack only, not by the droid acting on them.

### 2.4 Beacons (separate board)

`Beacon` advertises non-connectable manufacturer data (company ID `0x0183`) so droids react to a place or a personality:

| Item | Detail |
|------|--------|
| `Beacon::start(payload)` / `stop()` / `isAdvertising()` | Control advertising. |
| `Beacon::ensureRunning()` | Restart advertising if it stopped (watchdog). |
| `Beacon::msSinceStarted()` | Time since start or last restart. |
| `locationBeacon(location_id, interval, rssi_threshold, flag)` | Location beacon (type `0x0A`). |
| `personalityBeacon(Affiliation, chip_id, paired_with_remote)` | Personality beacon (type `0x03`). Affiliations: Scoundrel, Resistance, FirstOrder, Silent. Sixteen chip IDs (R-series default, BB-series default, Blue, Gray, Red, Orange, Purple, Black, CB-23, Yellow, C1-10P, D-O, Blue 2, BD-1, ALT, White Drum). |
| Keep-awake beacon | `personalityBeacon(Silent, kChipRSeriesDefault)`: droids ignore the affiliation but reset their sleep timer. |

The FTC robot has no environment-broadcast mechanism and nothing that reacts to one.

### 2.5 Timed, self-terminating motion

Every droid motion call takes a duration in milliseconds, blocks for it, then sends the stops. A call is a self-contained action, so a student can write `moveForward(1000)` and be done. The FTC model has no such primitive. Timed motion in FTC is built by the programmer (set power, wait on a timer or loop iterations, set power to 0).

### 2.6 Fixed arc manoeuvres (R2)

`driftClockwise` / `driftCounterClockwise` (default speed `0xa0`, inner wheel at half speed) and the one-wheel `turn*` calls are named presets of a wheel mix. FTC would express these with `arcadeDrive`'s two arguments.

### 2.7 Library-level conventions

- Return-value API: every method returns `bool` (success), with no exceptions. FTC OpModes get no success or failure from `setPower`; a hardware fault surfaces as an SDK exception or an error on the Driver Station.
- Config-driven defaults (`DroidDefaults`, personalities) generated from YAML. The FTC teleop hard-codes constants such as `LAUNCHER_TARGET_VELOCITY`.

## 3. FTC robot functionality missing from the droids

The task asked mainly for droid-only features, but the gap in the other direction decides what a common API can promise, so it is recorded here.

| FTC capability | Where it appears | Droid status |
|----------------|------------------|--------------|
| Gamepad input (`gamepad1.left_stick_y`, `right_stick_x`, triggers, bumpers) | `loop()` | None. Droid input is a program calling methods. Gamepad would have to be provided by the Pi runtime or a browser. |
| Continuous, per-loop control with immediate effect | `OpMode.loop()` | None. Commands are discrete BLE writes with a retry/reconnect path, so they cannot run at loop rates. |
| Encoder feedback (`getCurrentPosition`) | `UtilityTestHardware` | None. No odometry or position. Timed moves are open-loop. |
| Closed-loop velocity control (`DcMotorEx.setVelocity`, `getVelocity`, `RUN_USING_ENCODER`, PIDF coefficients) | Launcher | None. |
| Brake versus float (`ZeroPowerBehavior`) | Drive, intake | None. |
| Additional actuators: intake motor, continuous-rotation servos, launcher flywheel, feeder (windmill) servo | `intake`, `leftIntakeServo`, `rightIntakeServo`, `windmillServo`, `launcher` | None. The droid has only wheels, head (R2), and audio. |
| Positional `Servo` | `UtilityTestHardware` | None. |
| Sensors: `ColorSensor`, `DistanceSensor`, `TouchSensor`, `DigitalChannel`, `AnalogSensor`, `IMU`, `WebcamName` | `UtilityTestHardware` imports | None. The droid is blind. Obstacle avoidance, line following and heading hold are not possible without extra hardware. |
| Telemetry (`telemetry.addData`, `addLine`) | `loop()` | None in the library. `msSinceLastSuccess()`, RSSI from a scan and `checkAlive()` are the nearest health information. Application firmware may report separately (Wi-Fi, HTTP, Home Assistant are out of scope for the library). |
| Device discovery by configured name (`hardwareMap`) | `init()` | None. A droid exposes a fixed set of capabilities. |
| Lifecycle hooks (`init`, `init_loop`, `start`, `loop`, `stop`) and `@TeleOp` registration | OpMode | None. Phase 1 has the runtime own `main()` (inversion of control), so these would be provided by the runtime, not the droid. |
| Command-state feedback | SDK getters | Only a write-acknowledged boolean, and a raw notification callback that the library does not interpret. |

## 4. Implications for the common student API

1. **Safe common core.** `drive`/`arcade` style differential motion, a `stop`, and (with a timing helper) timed forward/backward/spin. Both sides can implement these. Map FTC's `-1..1` power to droid direction plus speed byte, with a deadband below about `0x60`.
2. **Timed versus continuous.** The Phase 1 runtime must either expose timed calls only, or batch a continuous `setPower` into periodic droid commands. At BLE rates (round trips, with up to 3 retries and a 1 s reconnect wait), a 50 Hz `loop()` is not realistic. This is the biggest design decision.
3. **Optional capabilities.** Audio, head control, beacons and connection health exist only on droids; encoders, velocity, sensors, gamepad, extra actuators and telemetry exist only on FTC. The API should either make them separate optional interfaces (`Audio`, `Head`, `Sensors`) or have the missing side throw or no-op in a documented way.
4. **Droid variants differ.** R2 has a real head motor and arc moves; BB has neither and turns its head with its body. A common "turn head" call would be a head motor on R2 and a body spin on BB.
5. **Errors and availability.** Droid calls can fail transiently (asleep, remote connected, dropped link) and return `false`. An FTC OpMode assumes the hardware is present. The runtime needs a policy for a droid dropping mid-program, and `checkAlive()` is the hook for the heartbeat.
6. **Hardware status.** Per `AGENTS.md`, wheel motion, BB behaviour, volume, `checkAlive()` reconnection, `scanForDroids()` and the beacon are compiled and unit-tested only. Only connect, audio and a head demo were run on a real R-series droid. Treat droid wheel semantics in this document as the library's intent, not confirmed behaviour.

## 5. Open questions

- TODO: Is the API timed-only, continuous-only, or both? (Section 4, item 2.)
- TODO: Does the student API expose droid-only features (audio, head) on the FTC side as no-ops, or only through a droid-specific interface?
- TODO: What FTC robot will be used in Phase 2? The repo holds only the StarterBot teleop; the TeamCode module is empty, so the actual mechanisms (and any sensors) are not yet known.
- TODO: Which gamepad or other input, if any, is available to student code in Phase 1?
