import static org.junit.Assert.assertTrue;

import org.junit.Test;
import robotics.MockRobot;

public class BeepTest {
    @Test
    public void beeps() throws Exception {
        MockRobot robot = new MockRobot();
        new Beep().run(robot);
        assertTrue("Expected the robot to beep, but beep() was never called", robot.beepCount() > 0);
    }
}
