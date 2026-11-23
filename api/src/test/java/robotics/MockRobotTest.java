package robotics;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.util.Arrays;
import org.junit.Test;

public class MockRobotTest {
    @Test public void recordsLogCallsInOrder() {
        MockRobot r = new MockRobot();
        r.log("a");
        r.log("b");
        assertEquals(Arrays.asList("a", "b"), r.messages());
    }

    @Test public void recordsHeadAndBeep() {
        MockRobot r = new MockRobot();
        r.rotateHead(-1);
        r.centerHead();
        r.beep(5);
        assertEquals(Arrays.asList(-1), r.headRotations());
        assertEquals(1, r.centerCount());
        assertEquals(1, r.beepCount());
        assertEquals(Arrays.asList(5), r.beepSounds());
    }

    @Test public void messagesIsASnapshot() {
        MockRobot r = new MockRobot();
        r.log("a");
        java.util.List<String> snap = r.messages();
        r.log("b");
        assertEquals(1, snap.size());
    }

    @Test public void programRunnerLoadsAndRuns() throws Exception {
        Program p = ProgramRunner.load(Hello.class.getName(), getClass().getClassLoader());
        MockRobot r = new MockRobot();
        ProgramRunner.run(p, r);
        assertTrue(r.messages().contains("hi"));
    }

    @Test(expected = IllegalArgumentException.class)
    public void programRunnerRejectsNonPrograms() throws Exception {
        ProgramRunner.load("java.lang.String", getClass().getClassLoader());
    }

    public static class Hello implements Program {
        @Override public void run(Robot robot) { robot.log("hi"); }
    }
}
