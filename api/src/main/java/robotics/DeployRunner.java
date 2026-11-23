package robotics;

/**
 * Runs a student's {@link Program} on a real droid through the Pi's board controller. The classroom
 * server starts this in its own JVM for the Hardware tab's Deploy button, and stops the droid again
 * if the JVM is killed.
 *
 * Usage: java -cp student.jar:robotics-api.jar robotics.DeployRunner ClassName boardId controllerUrl
 *
 * Output (robot.log and link problems) goes to stdout. Exit code 0 when run() returns normally, 1 when
 * it throws, 2 for bad usage. Either way the motors are stopped before the JVM exits.
 */
public final class DeployRunner {
    private DeployRunner() {}

    public static void main(String[] args) {
        if (args.length != 3) {
            System.err.println("usage: DeployRunner <ClassName> <boardId> <controllerUrl>");
            System.exit(2);
        }
        System.exit(run(args[0], args[1], args[2]));
    }

    static int run(String className, String boardId, String controllerUrl) {
        java.util.function.Consumer<String> out = new java.util.function.Consumer<String>() {
            @Override public void accept(String s) { System.out.println(s); System.out.flush(); }
        };
        Program program;
        try {
            program = ProgramRunner.load(className, Thread.currentThread().getContextClassLoader());
        } catch (Throwable t) {
            out.accept("Could not load " + className + ": " + t);
            return 1;
        }
        DroidRobot robot = new DroidRobot(new ControllerDroidLink(controllerUrl, boardId, out), out,
                DroidRobot.DEFAULT_RAMP_MS);
        try {
            ProgramRunner.run(program, robot);
            return 0;
        } catch (Throwable t) {
            out.accept("Your program stopped with an error: " + t);
            StackTraceElement[] st = t.getStackTrace();
            for (int i = 0; i < st.length && i < 8; i++) out.accept("    at " + st[i]);
            return 1;
        } finally {
            robot.close();
        }
    }
}
