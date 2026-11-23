package robotics;

import java.io.Closeable;
import java.util.function.Consumer;

/**
 * A Galaxy's Edge droid presented through the same {@link Robot} contract as the FTC StarterBot.
 *
 * What makes the droid look like an FTC drive train:
 * <ul>
 *   <li><b>Power model.</b> {@code setPower(-1..1)} sets a persistent motor state, exactly like
 *       FTC. Nothing here is timed; the motor runs until the program sets a new power.</li>
 *   <li><b>Wiring.</b> On the StarterBot the right motor is wired backwards, so programs call
 *       {@code rightDrive().setDirection(REVERSE)}. The droid's firmware already treats "forward"
 *       as robot-forward on both sides, so this class models the right motor as wired reversed.
 *       The same student code then drives forward on both robots, and code that forgets the
 *       REVERSE call spins in circles on both.</li>
 *   <li><b>Synchronous.</b> Every command blocks until the droid controller has finished it:
 *       {@code setPower} returns once the motor write is acknowledged, {@code rotateHead} once the head
 *       has turned, and so on. Writes that would not change anything are skipped, because FTC code sets
 *       power on every {@code loop()} pass and BLE writes are slow.</li>
 * </ul>
 *
 * Where the droid cannot match FTC:
 * <ul>
 *   <li><b>Resolution.</b> The droid uses only the high nibble of the speed byte and does not move
 *       below 0x60, so there are 10 non-zero speeds per direction, and powers under
 *       {@value #DEADBAND} stop the motor.</li>
 *   <li><b>Zero-power behaviour.</b> The droid cannot truly brake or float. BRAKE stops with a
 *       0 ms ramp, anything else stops with the droid's default 300 ms ramp. Not tested on a droid.</li>
 *   <li><b>Failures.</b> Writes can fail (droid asleep, remote connected, link dropped). FTC has no
 *       equivalent, so a failed write is retried a few times and then logged and dropped. The next
 *       command that needs the same state tries again.</li>
 *   <li><b>Safety.</b> Droid motors never stop on their own. Call {@link #close()} when the program
 *       ends; it sends stops. A JVM shutdown hook does the same on a normal or SIGTERM exit, but not
 *       on SIGKILL, so a killed program can leave a droid driving until the link or the droid's own
 *       power is cut. A watchdog on the ESP32 would close that gap.</li>
 * </ul>
 */
public class DroidRobot implements Robot, Closeable {
    /** Powers with a smaller magnitude than this stop the motor instead of mapping to the minimum speed. */
    public static final double DEADBAND = 0.05;

    /** Ramp the droid uses to stop when zero-power behaviour is not BRAKE (its stock default). */
    static final int DEFAULT_STOP_RAMP_MS = 300;
    static final int DEFAULT_RAMP_MS = 100;
    private static final long RETRY_DELAY_MS = 250;
    private static final int ATTEMPTS = 3;

    private final DroidLink link;
    private final Consumer<String> logger;
    private final int rampMs;
    private final Object lock = new Object();
    private final Motor left = new Motor(DroidLink.MOTOR_LEFT, false);
    private final Motor right = new Motor(DroidLink.MOTOR_RIGHT, true);
    private final Thread shutdownHook;
    /** One-shot droid actions (not motor state). */
    private enum Action { BEEP, HEAD_LEFT, HEAD_RIGHT, HEAD_CENTER }
    private static final int NO_SOUND = -1;
    private boolean closed;   // guarded by lock
    private boolean failing;  // guarded by lock; true while the link is rejecting writes

    public DroidRobot(DroidLink link) {
        this(link, new Consumer<String>() {
            @Override public void accept(String s) { System.out.println(s); }
        }, DEFAULT_RAMP_MS);
    }

    /**
     * @param logger        receives {@link #log} messages and link-failure notices
     * @param rampMs        ramp for speed changes (FTC changes power immediately; a small ramp is
     *                      kinder to a toy droid. Untested on hardware)
     */
    public DroidRobot(DroidLink link, Consumer<String> logger, int rampMs) {
        if (link == null) throw new IllegalArgumentException("link");
        this.link = link;
        this.logger = logger;
        this.rampMs = rampMs;
        shutdownHook = new Thread(new Runnable() {
            @Override public void run() { closeQuietly(); }
        }, "droid-shutdown");
        Runtime.getRuntime().addShutdownHook(shutdownHook);
    }

    @Override public void log(String message) { logger.accept(message); }

    @Override public DriveMotor leftDrive() { return left; }

    @Override public DriveMotor rightDrive() { return right; }

    /** Blocks until the head has finished turning. 1 = right, -1 = left. */
    @Override public void rotateHead(int direction) {
        if (direction != 1 && direction != -1) throw new IllegalArgumentException("direction must be 1 or -1");
        act(direction == 1 ? Action.HEAD_RIGHT : Action.HEAD_LEFT);
    }

    /** Blocks until the head is centered. */
    @Override public void centerHead() { act(Action.HEAD_CENTER); }

    /** Blocks until the droid has played the sound. {@code sound} indexes the droid's personality sounds. */
    @Override public void beep(int sound) {
        if (sound < 0) throw new IllegalArgumentException("sound must be 0 or more");
        act(Action.BEEP, sound);
    }

    private void act(Action a) { act(a, NO_SOUND); }

    private void act(Action a, int sound) {
        synchronized (lock) {
            if (closed) return;
            send(null, null, a, sound);
        }
    }

    /** Stop both motors and send the stops. Safe to call more than once. */
    @Override public void close() {
        synchronized (lock) {
            if (closed) return;
            left.power = 0;
            right.power = 0;
            closed = true;
            if (!syncMotors()) log("could not stop the droid motors; power the droid off");
        }
        try {
            Runtime.getRuntime().removeShutdownHook(shutdownHook);
        } catch (IllegalStateException e) {
            // already shutting down: we are the hook
        }
    }

    private void closeQuietly() {
        try {
            close();
        } catch (RuntimeException e) {
            // nothing useful to do during shutdown
        }
    }

    // ---- power model -------------------------------------------------------

    /** Map |power| in [0, 1] to the droid speed byte: 0 below the deadband, else 0x60..0xf0. */
    static int speedFor(double magnitude) {
        if (!(magnitude >= DEADBAND)) return 0;  // also catches NaN
        int nibble = 6 + (int) Math.round(Math.min(1.0, magnitude) * 9);
        return nibble << 4;
    }

    private static final class Out {
        final int speed;
        final boolean backward;
        final int ramp;

        Out(int speed, boolean backward, int ramp) {
            this.speed = speed;
            this.backward = speed != 0 && backward;  // a stop has no direction
            this.ramp = ramp;
        }

        boolean sameMotion(Out o) { return speed == o.speed && backward == o.backward; }
    }

    private final class Motor implements DriveMotor {
        final int id;
        final boolean wiredReversed;
        // guarded by lock
        double power;
        Direction direction = Direction.FORWARD;
        ZeroPowerBehavior zeroPower = ZeroPowerBehavior.UNKNOWN;
        Out sent = new Out(0, false, 0);  // droids are assumed stopped at connect

        Motor(int id, boolean wiredReversed) {
            this.id = id;
            this.wiredReversed = wiredReversed;
        }

        Out desired() {  // call with lock held
            int speed = speedFor(Math.abs(power));
            boolean backward = (power < 0) ^ (direction == Direction.REVERSE) ^ wiredReversed;
            int ramp = speed != 0 ? rampMs : (zeroPower == ZeroPowerBehavior.BRAKE ? 0 : DEFAULT_STOP_RAMP_MS);
            return new Out(speed, backward, ramp);
        }

        boolean pending() { return !desired().sameMotion(sent); }

        @Override public void setPower(double p) {
            if (Double.isNaN(p)) p = 0;
            synchronized (lock) {
                if (closed) return;  // close() has already stopped the motors; stay stopped
                power = Math.max(-1.0, Math.min(1.0, p));
                syncMotors();
            }
        }

        @Override public double getPower() { synchronized (lock) { return power; } }

        @Override public void setDirection(Direction d) {
            if (d == null) throw new IllegalArgumentException("direction");
            synchronized (lock) {
                direction = d;
                syncMotors();
            }
        }

        @Override public Direction getDirection() { synchronized (lock) { return direction; } }

        @Override public void setZeroPowerBehavior(ZeroPowerBehavior b) {
            if (b == null) throw new IllegalArgumentException("behavior");
            synchronized (lock) {
                zeroPower = b;
                syncMotors();
            }
        }

        @Override public ZeroPowerBehavior getZeroPowerBehavior() { synchronized (lock) { return zeroPower; } }
    }

    // ---- link writes (all with lock held) -----------------------------------

    /** The motor that needs a write, stops first. */
    private Motor nextPending() {
        Motor[] all = {left, right};
        for (Motor m : all) {
            if (m.pending() && m.desired().speed == 0) return m;
        }
        for (Motor m : all) {
            if (m.pending()) return m;
        }
        return null;
    }

    /** Write every motor change the droid has not seen yet. @return false if the link gave up. */
    private boolean syncMotors() {
        Motor m;
        while ((m = nextPending()) != null) {
            Out out = m.desired();
            if (!send(m, out, null, NO_SOUND)) return false;
            m.sent = out;
        }
        return true;
    }

    /** One link write (a motor change or an action), retried a few times. */
    private boolean send(Motor m, Out out, Action act, int sound) {
        for (int attempt = 1; attempt <= ATTEMPTS; attempt++) {
            boolean ok = false;
            try {
                ok = m != null ? link.sendMotor(m.id, out.backward, out.speed, out.ramp) : perform(act, sound);
            } catch (RuntimeException e) {
                log("droid link error: " + e);
            }
            if (ok) {
                if (failing) log("droid link recovered");
                failing = false;
                return true;
            }
            if (!failing) log("droid did not accept a command; retrying");
            failing = true;
            if (attempt < ATTEMPTS) {
                try {
                    Thread.sleep(RETRY_DELAY_MS);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return false;
                }
            }
        }
        log("droid did not respond; giving up on this command");
        return false;
    }

    private boolean perform(Action a, int sound) {
        switch (a) {
            case HEAD_LEFT: return link.rotateHead(false);
            case HEAD_RIGHT: return link.rotateHead(true);
            case HEAD_CENTER: return link.centerHead();
            default: return link.sendBeep(sound);
        }
    }
}
