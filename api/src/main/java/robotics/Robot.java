package robotics;

/** What a program can do with a robot (apiVersion 0). */
public interface Robot {
    /** Hello world output goes here. */
    void log(String message);

    /**
     * The left drive motor. On an FTC robot this is the motor configured as "left_drive".
     *
     * As on the FTC StarterBot, a program normally sets {@code rightDrive().setDirection(REVERSE)}
     * once at the start so that positive power drives the robot forward.
     */
    DriveMotor leftDrive();

    /** The right drive motor ("right_drive" on the FTC StarterBot). */
    DriveMotor rightDrive();
}
