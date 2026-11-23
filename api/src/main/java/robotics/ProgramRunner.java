package robotics;

/**
 * The harness's entry point: loads a student class, instantiates it and calls run(Robot).
 * Test uses a MockRobot; a later phase swaps in the real runtime.
 *
 * Usage: java -cp ... robotics.ProgramRunner ClassName
 */
public final class ProgramRunner {
    private ProgramRunner() {}

    /** Instantiate the named class (which must implement Program). */
    public static Program load(String className, ClassLoader loader) throws Exception {
        Class<?> c = Class.forName(className, true, loader);
        if (!Program.class.isAssignableFrom(c)) {
            throw new IllegalArgumentException(className + " does not implement robotics.Program");
        }
        return (Program) c.getDeclaredConstructor().newInstance();
    }

    public static void run(Program program, Robot robot) throws Exception {
        program.run(robot);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("usage: ProgramRunner <ClassName>");
            System.exit(2);
        }
        Program p = load(args[0], Thread.currentThread().getContextClassLoader());
        run(p, new MockRobot() {
            @Override
            public void log(String message) {
                super.log(message);
                System.out.println(message);
            }
        });
    }
}
