package robotics;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;
import org.junit.After;
import org.junit.Test;

public class DroidRobotTest {
    /** Records every write; can be told to fail. */
    static class FakeLink implements DroidLink {
        final List<int[]> sent = Collections.synchronizedList(new ArrayList<int[]>());
        final AtomicBoolean fail = new AtomicBoolean(false);

        @Override public boolean sendMotor(int motor, boolean backward, int speed, int rampMs) {
            if (fail.get()) return false;
            sent.add(new int[] {motor, backward ? 1 : 0, speed, rampMs});
            return true;
        }

        int[] last() { return sent.get(sent.size() - 1); }
    }

    private final FakeLink link = new FakeLink();
    private final List<String> logs = Collections.synchronizedList(new ArrayList<String>());
    private DroidRobot robot;

    private DroidRobot robot() {
        robot = new DroidRobot(link, new Consumer<String>() {
            @Override public void accept(String s) { logs.add(s); }
        }, 100, 0);
        return robot;
    }

    @After public void tearDown() { if (robot != null) robot.close(); }

    private void settle(DroidRobot r) throws Exception { assertTrue(r.flush(2000)); }

    @Test public void speedMappingUsesHighNibbleAndDeadband() {
        assertEquals(0, DroidRobot.speedFor(0.0));
        assertEquals(0, DroidRobot.speedFor(0.04));
        assertEquals(0x60, DroidRobot.speedFor(0.05));
        assertEquals(0xf0, DroidRobot.speedFor(1.0));
        assertEquals(0xf0, DroidRobot.speedFor(5.0));
        assertEquals(0, DroidRobot.speedFor(Double.NaN));
        for (double p = 0.05; p <= 1.0; p += 0.01) {
            int s = DroidRobot.speedFor(p);
            assertTrue(s >= 0x60 && (s & 0x0f) == 0);
        }
    }

    @Test public void starterBotInitDrivesBothSidesForward() throws Exception {
        DroidRobot r = robot();
        r.leftDrive().setDirection(DriveMotor.Direction.FORWARD);
        r.rightDrive().setDirection(DriveMotor.Direction.REVERSE);  // as in BioBuzzStarterbotTeleop
        r.leftDrive().setPower(0.5);
        r.rightDrive().setPower(0.5);
        settle(r);
        assertEquals(2, link.sent.size());
        for (int[] c : link.sent) assertEquals("forward", 0, c[1]);
        assertEquals(0xb0, link.last()[2]);
    }

    @Test public void forgettingReverseSpinsLikeFtc() throws Exception {
        DroidRobot r = robot();
        r.leftDrive().setPower(0.5);
        r.rightDrive().setPower(0.5);
        settle(r);
        int right = 0, left = 0;
        for (int[] c : link.sent) {
            if (c[0] == DroidLink.MOTOR_RIGHT) right = c[1]; else left = c[1];
        }
        assertEquals(0, left);
        assertEquals(1, right);
    }

    @Test public void negativePowerGoesBackward() throws Exception {
        DroidRobot r = robot();
        r.rightDrive().setDirection(DriveMotor.Direction.REVERSE);
        r.leftDrive().setPower(-1);
        r.rightDrive().setPower(-1);
        settle(r);
        for (int[] c : link.sent) assertEquals(1, c[1]);
    }

    @Test public void arcadeDriveMixing() throws Exception {
        DroidRobot r = robot();
        r.rightDrive().setDirection(DriveMotor.Direction.REVERSE);
        double forward = 0.0, rotate = 1.0;  // spin in place
        r.leftDrive().setPower(forward + rotate);
        r.rightDrive().setPower(forward - rotate);
        settle(r);
        int[] l = null, rt = null;
        for (int[] c : link.sent) { if (c[0] == 0) l = c; else rt = c; }
        assertEquals(0, l[1]);
        assertEquals(1, rt[1]);
    }

    @Test public void repeatedSetPowerSendsOnlyOnce() throws Exception {
        DroidRobot r = robot();
        for (int i = 0; i < 100; i++) r.leftDrive().setPower(0.7);
        settle(r);
        Thread.sleep(50);
        assertEquals(1, link.sent.size());
        // a change within one speed step is also not worth a write
        r.leftDrive().setPower(0.71);
        settle(r);
        Thread.sleep(50);
        assertEquals(1, link.sent.size());
    }

    @Test public void stopUsesZeroPowerBehaviorForRamp() throws Exception {
        DroidRobot r = robot();
        r.leftDrive().setZeroPowerBehavior(DriveMotor.ZeroPowerBehavior.BRAKE);
        r.leftDrive().setPower(1);
        settle(r);
        r.leftDrive().setPower(0);
        settle(r);
        int[] stop = link.last();
        assertEquals(0, stop[2]);
        assertEquals(0, stop[1]);
        assertEquals(0, stop[3]);

        r.rightDrive().setPower(1);
        settle(r);
        r.rightDrive().setPower(0);
        settle(r);
        assertEquals(300, link.last()[3]);
    }

    @Test public void getPowerReturnsRequestedClampedValue() {
        DroidRobot r = robot();
        r.leftDrive().setPower(3);
        assertEquals(1.0, r.leftDrive().getPower(), 0);
        r.leftDrive().setPower(0.01);
        assertEquals(0.01, r.leftDrive().getPower(), 0);  // deadband applies to the droid, not the readback
        assertEquals(DriveMotor.Direction.FORWARD, r.leftDrive().getDirection());
        assertEquals(DriveMotor.ZeroPowerBehavior.UNKNOWN, r.leftDrive().getZeroPowerBehavior());
    }

    @Test public void closeStopsRunningMotorsAndIgnoresLaterPower() throws Exception {
        DroidRobot r = robot();
        r.leftDrive().setPower(1);
        r.rightDrive().setPower(1);
        settle(r);
        r.close();
        int stops = 0;
        for (int[] c : link.sent) if (c[2] == 0) stops++;
        assertEquals(2, stops);
        r.leftDrive().setPower(1);
        Thread.sleep(50);
        assertEquals(4, link.sent.size());
    }

    @Test public void retriesAfterLinkFailureAndLogsOnce() throws Exception {
        link.fail.set(true);
        DroidRobot r = robot();
        r.leftDrive().setPower(1);
        assertFalse(r.flush(100));
        link.fail.set(false);
        assertTrue(r.flush(3000));
        assertEquals(1, link.sent.size());
        assertEquals(1, countContaining("did not accept"));
        assertEquals(1, countContaining("recovered"));
    }

    private int countContaining(String s) {
        int n = 0;
        synchronized (logs) { for (String l : logs) if (l.contains(s)) n++; }
        return n;
    }

    @Test public void stopsAreSentBeforeStarts() throws Exception {
        link.fail.set(true);
        DroidRobot r = robot();
        r.leftDrive().setPower(1);
        r.rightDrive().setPower(1);
        link.fail.set(false);
        assertTrue(r.flush(3000));
        link.sent.clear();
        link.fail.set(true);
        r.leftDrive().setPower(1.0);   // unchanged
        r.leftDrive().setPower(0.0);   // stop left
        r.rightDrive().setPower(-1);   // reverse right
        link.fail.set(false);
        assertTrue(r.flush(3000));
        assertEquals(0, link.sent.get(0)[0]);
        assertEquals(0, link.sent.get(0)[2]);
    }
}
