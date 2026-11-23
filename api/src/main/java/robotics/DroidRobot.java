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
 *   <li><b>Non-blocking.</b> {@code setPower} returns immediately. A sender thread forwards changes
 *       to the {@link DroidLink} and skips writes that would not change anything, because FTC
 *       code sets power on every {@code loop()} pass and BLE writes are slow.</li>
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
 *       equivalent, so failures are logged and retried, and {@link #flush} reports whether the
 *       droid caught up.</li>
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
    static final long DEFAULT_MIN_INTERVAL_MS = 20;
    private static final long RETRY_DELAY_MS = 250;
    private static final int CLOSE_ATTEMPTS = 3;
    private static final long CLOSE_TIMEOUT_MS = 5000;

    private final DroidLink link;
    private final Consumer<String> logger;
    private final int rampMs;
    private final long minIntervalMs;
    private final Object lock = new Object();
    private final Motor left = new Motor(DroidLink.MOTOR_LEFT, false);
    private final Motor right = new Motor(DroidLink.MOTOR_RIGHT, true);
    private final Thread sender;
    private final Thread shutdownHook;
    private boolean closed;

    public DroidRobot(DroidLink link) {
        this(link, new Consumer<String>() {
            @Override public void accept(String s) { System.out.println(s); }
        }, DEFAULT_RAMP_MS, DEFAULT_MIN_INTERVAL_MS);
    }

    /**
     * @param logger        receives {@link #log} messages and link-failure notices
     * @param rampMs        ramp for speed changes (FTC changes power immediately; a small ramp is
     *                      kinder to a toy droid. Untested on hardware)
     * @param minIntervalMs minimum gap between BLE writes
     */
    public DroidRobot(DroidLink link, Consumer<String> logger, int rampMs, long minIntervalMs) {
        if (link == null) throw new IllegalArgumentException("link");
        this.link = link;
        this.logger = logger;
        this.rampMs = rampMs;
        this.minIntervalMs = minIntervalMs;
        sender = new Thread(new Runnable() {
            @Override public void run() { senderLoop(); }
        }, "droid-sender");
        sender.setDaemon(true);
        sender.start();
        shutdownHook = new Thread(new Runnable() {
            @Override public void run() { closeQuietly(); }
        }, "droid-shutdown");
        Runtime.getRuntime().addShutdownHook(shutdownHook);
    }

    @Override public void log(String message) { logger.accept(message); }

    @Override public DriveMotor leftDrive() { return left; }

    @Override public DriveMotor rightDrive() { return right; }

    /**
     * Wait until every requested motor state has been sent to the droid.
     *
     * @return true if the droid is up to date, false on timeout (for example the link is down)
     */
    public boolean flush(long timeoutMs) throws InterruptedException {
        long deadline = System.currentTimeMillis() + timeoutMs;
        synchronized (lock) {
            while (nextPending() != null) {
                long remaining = deadline - System.currentTimeMillis();
                if (remaining <= 0) return false;
                lock.wait(remaining);
            }
            return true;
        }
    }

    /** Stop both motors, send the stops, and shut the sender down. Safe to call more than once. */
    @Override public void close() {
        synchronized (lock) {
            if (closed) return;
            left.power = 0;
            right.power = 0;
            closed = true;
            lock.notifyAll();
        }
        try {
            Runtime.getRuntime().removeShutdownHook(shutdownHook);
        } catch (IllegalStateException e) {
            // already shutting down: we are the hook
        }
        try {
            sender.join(CLOSE_TIMEOUT_MS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
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
                lock.notifyAll();
            }
        }

        @Override public double getPower() { synchronized (lock) { return power; } }

        @Override public void setDirection(Direction d) {
            if (d == null) throw new IllegalArgumentException("direction");
            synchronized (lock) {
                direction = d;
                lock.notifyAll();
            }
        }

        @Override public Direction getDirection() { synchronized (lock) { return direction; } }

        @Override public void setZeroPowerBehavior(ZeroPowerBehavior b) {
            if (b == null) throw new IllegalArgumentException("behavior");
            synchronized (lock) {
                zeroPower = b;
                lock.notifyAll();
            }
        }

        @Override public ZeroPowerBehavior getZeroPowerBehavior() { synchronized (lock) { return zeroPower; } }
    }

    // ---- sender thread -----------------------------------------------------

    /** The motor that needs a write, stops first. Call with lock held. */
    private Motor nextPending() {
        boolean lp = left.pending();
        boolean rp = right.pending();
        if (lp && left.desired().speed == 0) return left;
        if (rp && right.desired().speed == 0) return right;
        if (lp) return left;
        if (rp) return right;
        return null;
    }

    private void senderLoop() {
        boolean failing = false;
        int closeFailures = 0;
        try {
            while (true) {
                Motor m;
                Out out;
                synchronized (lock) {
                    m = nextPending();
                    while (m == null) {
                        if (closed) return;
                        lock.wait();
                        m = nextPending();
                    }
                    out = m.desired();
                }
                boolean ok = false;
                try {
                    ok = link.sendMotor(m.id, out.backward, out.speed, out.ramp);
                } catch (RuntimeException e) {
                    log("droid link error: " + e);
                }
                synchronized (lock) {
                    if (ok) m.sent = out;
                    lock.notifyAll();
                    if (!ok && closed && ++closeFailures >= CLOSE_ATTEMPTS) {
                        log("could not stop the droid motors; power the droid off");
                        return;
                    }
                }
                if (ok) {
                    if (failing) log("droid link recovered");
                    failing = false;
                    sleep(minIntervalMs);
                } else {
                    if (!failing) log("droid did not accept a motor command; retrying");
                    failing = true;
                    sleep(RETRY_DELAY_MS);
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static void sleep(long ms) throws InterruptedException {
        if (ms > 0) Thread.sleep(ms);
    }
}
