package robotics;

/**
 * One drive motor, with the same contract as the FTC SDK's {@code DcMotor} (the subset needed
 * for driving): power in [-1, 1], a direction flip, and a zero-power behaviour.
 *
 * Like FTC, setting a power is not a one-shot move: the motor keeps running at that power until
 * the next call. Programs must set power to 0 to stop.
 */
public interface DriveMotor {
    /** Same meaning as FTC's DcMotor.Direction: FORWARD is the motor's natural direction. */
    enum Direction { FORWARD, REVERSE }

    /** Same meaning as FTC's DcMotor.ZeroPowerBehavior. UNKNOWN is the initial value. */
    enum ZeroPowerBehavior { UNKNOWN, BRAKE, FLOAT }

    /** Set the power, clamped to [-1, 1]. Positive is the direction set by {@link #setDirection}. */
    void setPower(double power);

    /** The power last set (after clamping), as FTC does. Not a measurement. */
    double getPower();

    void setDirection(Direction direction);

    Direction getDirection();

    void setZeroPowerBehavior(ZeroPowerBehavior behavior);

    ZeroPowerBehavior getZeroPowerBehavior();
}
