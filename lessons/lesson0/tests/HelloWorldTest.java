import static org.junit.Assert.assertTrue;

import org.junit.Test;
import robotics.MockRobot;

public class HelloWorldTest {
    @Test
    public void logsHello() throws Exception {
        MockRobot robot = new MockRobot();
        new HelloWorld().run(robot);
        assertTrue("Expected the robot to log \"Hello, world!\", but it logged: " + robot.messages(),
                robot.messages().contains("Hello, world!"));
    }
}
