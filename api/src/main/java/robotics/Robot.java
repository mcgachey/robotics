package robotics;

/**
 * Your robot! Your program gets a Robot, and you tell it what to do by calling the methods below.
 *
 * <p>Some robots can do more than others. A droid can turn its head and beep. A wheeled robot
 * (the FTC StarterBot) can drive, but it has no head and no speaker. If you ask a robot to do
 * something it can't do, you get an {@code UnsupportedOperationException} (that is Java's way of
 * saying "this robot can't do that").
 */
public interface Robot {
    /** Writes a message so you can read it. Use this for your "Hello, world!" program. */
    void log(String message);

    /**
     * Gives you the left wheel motor. On a StarterBot this is the motor named "left_drive".
     *
     * <p>Tip: the right motor is mounted facing the other way. At the start of your program, call
     * {@code rightDrive().setDirection(REVERSE)}. After that, a positive power makes the robot
     * drive forward.
     */
    DriveMotor leftDrive();

    /** Gives you the right wheel motor. On a StarterBot this is the motor named "right_drive". */
    DriveMotor rightDrive();

    /**
     * Turns the droid's head for a short time (1.5 seconds), then stops. Your program does not
     * wait. It moves on to the next line while the head turns. Head and beep jobs happen one
     * after another, in the order you gave them. Only droids have a head.
     *
     * @param direction use 1 to turn right, or -1 to turn left
     * @throws IllegalArgumentException if direction is not 1 or -1
     * @throws UnsupportedOperationException if this robot has no head
     */
    void rotateHead(int direction);

    /**
     * Turns the droid's head back to face the front. Your program does not wait. Only droids have
     * a head.
     *
     * @throws UnsupportedOperationException if this robot has no head
     */
    void centerHead();

    /**
     * Plays a sound. Your program waits until the sound is finished, then moves on. Only droids
     * can beep.
     *
     * @param sound which sound to play. Start with 0, then try 1, 2, 3 and so on.
     * @throws IllegalArgumentException if sound is less than 0
     * @throws UnsupportedOperationException if this robot cannot beep
     */
    void beep(int sound);
}
