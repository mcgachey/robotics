package robotics;

/**
 * One wheel motor. You get one from {@link Robot#leftDrive()} or {@link Robot#rightDrive()}.
 *
 * <p>Power is a number from -1 to 1. Positive spins the wheel one way, negative spins it the
 * other way, and 0 means stop.
 *
 * <p>Careful: the motor keeps spinning at the power you set until you set a new power. To make
 * the robot stop, set the power to 0.
 */
public interface DriveMotor {
    /** Which way the motor spins when the power is positive. FORWARD is the normal way. */
    enum Direction { FORWARD, REVERSE }

    /** What the motor does when the power is 0: BRAKE stops it quickly, FLOAT lets it coast. UNKNOWN is what you get before you choose. */
    enum ZeroPowerBehavior { UNKNOWN, BRAKE, FLOAT }

    /** Sets how hard the motor spins, from -1 to 1. Bigger numbers than that are cut down to 1 (or -1). Positive power spins the way set by {@link #setDirection}. */
    void setPower(double power);

    /** Tells you the power you last set. It is not a measurement of how fast the wheel is really turning. */
    double getPower();

    /** Chooses which way the motor spins when the power is positive. */
    void setDirection(Direction direction);

    /** Tells you which direction you chose. */
    Direction getDirection();

    /** Chooses what the motor does when the power is 0. */
    void setZeroPowerBehavior(ZeroPowerBehavior behavior);

    /** Tells you what you chose for when the power is 0. */
    ZeroPowerBehavior getZeroPowerBehavior();
}
