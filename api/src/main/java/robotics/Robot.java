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

    /**
     * Rotate the head for a short, fixed time (1.5 seconds at a fixed speed), then stop it. Returns
     * immediately; the droid does the turn in the background, in order with other head and beep
     * commands. Droid only; the FTC StarterBot has no head.
     *
     * @param direction 1 to turn right, -1 to turn left
     * @throws IllegalArgumentException if direction is not 1 or -1
     * @throws UnsupportedOperationException on a robot without a head
     */
    void rotateHead(int direction);

    /**
     * Return the head to the center position. Returns immediately. Droid only.
     *
     * @throws UnsupportedOperationException on a robot without a head
     */
    void centerHead();

    /**
     * Play one of the droid's sounds. On a droid this blocks until the sound has finished. Droid
     * only; the FTC StarterBot has no speaker.
     *
     * @param sound index into the droid's personality sounds, 0 or more
     * @throws IllegalArgumentException if {@code sound} is negative
     * @throws UnsupportedOperationException on a robot that cannot beep
     */
    void beep(int sound);
}
