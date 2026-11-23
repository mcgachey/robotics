package robotics;

import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** A Robot that records what a program does. Used by Test. */
public class MockRobot implements Robot {
    private final List<String> messages = new ArrayList<String>();
    private final MockDriveMotor leftDrive = new MockDriveMotor();
    private final MockDriveMotor rightDrive = new MockDriveMotor();
    private final List<Integer> headMoves = new ArrayList<Integer>();
    private int centers;
    private final List<Integer> beepSounds = new ArrayList<Integer>();

    @Override
    public MockDriveMotor leftDrive() {
        return leftDrive;
    }

    @Override
    public MockDriveMotor rightDrive() {
        return rightDrive;
    }

    @Override public synchronized void rotateHead(int direction) {
        if (direction != 1 && direction != -1) throw new IllegalArgumentException("direction must be 1 or -1");
        headMoves.add(direction);
    }

    @Override public synchronized void centerHead() { centers++; }

    @Override public synchronized void beep(int sound) {
        if (sound < 0) throw new IllegalArgumentException("sound must be 0 or more");
        beepSounds.add(sound);
    }

    /** The directions (1 or -1) passed to {@link #rotateHead}, in order. */
    public synchronized List<Integer> headRotations() { return new ArrayList<Integer>(headMoves); }

    /** How many times {@link #centerHead} was called. */
    public synchronized int centerCount() { return centers; }

    /** How many times {@link #beep} was called. */
    public synchronized int beepCount() { return beepSounds.size(); }

    /** The sound indexes passed to {@link #beep}, in order. */
    public synchronized List<Integer> beepSounds() { return new ArrayList<Integer>(beepSounds); }

    /** A drive motor that just remembers its settings (power is clamped as on a real motor). */
    public static class MockDriveMotor implements DriveMotor {
        private double power;
        private Direction direction = Direction.FORWARD;
        private ZeroPowerBehavior zeroPower = ZeroPowerBehavior.UNKNOWN;

        @Override public synchronized void setPower(double p) {
            power = Math.max(-1.0, Math.min(1.0, p));
        }
        @Override public synchronized double getPower() { return power; }
        @Override public synchronized void setDirection(Direction d) { direction = d; }
        @Override public synchronized Direction getDirection() { return direction; }
        @Override public synchronized void setZeroPowerBehavior(ZeroPowerBehavior b) { zeroPower = b; }
        @Override public synchronized ZeroPowerBehavior getZeroPowerBehavior() { return zeroPower; }
    }

    @Override
    public synchronized void log(String message) {
        messages.add(message);
        appendToLogFile(message);
    }

    /**
     * If the harness set -Drobotics.logFile=PATH, also append each message there (one per line) so the
     * server can show the student what their program logged. Failures here never affect the program.
     */
    private static void appendToLogFile(String message) {
        String path = System.getProperty("robotics.logFile");
        if (path == null || path.isEmpty()) return;
        try (Writer w = new OutputStreamWriter(new FileOutputStream(path, true), "UTF-8")) {
            w.write(String.valueOf(message));
            w.write("\n");
        } catch (IOException e) {
            // ignore: logging is best-effort
        }
    }

    /** A snapshot of the messages logged so far, in order. */
    public synchronized List<String> messages() {
        return Collections.unmodifiableList(new ArrayList<String>(messages));
    }
}
