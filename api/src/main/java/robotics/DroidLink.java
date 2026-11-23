package robotics;

/**
 * The wire to a droid, as seen by {@link DroidRobot}. One method per ESP32 firmware primitive.
 *
 * The real implementation (Pi to ESP32 transport) is not written yet; it forwards to
 * libastromech's {@code Astromech::sendMotor(direction, motor, speed, ramp_ms)}. Tests use a fake.
 *
 * Implementations may block (the BLE write can take a while and retries internally).
 * {@link DroidRobot} calls this synchronously from the student's thread, one call at a time.
 */
public interface DroidLink {
    int MOTOR_LEFT = 0;
    int MOTOR_RIGHT = 1;

    /**
     * Start, change or stop one motor. Speed 0 stops it. Motors keep running until told otherwise.
     *
     * @param motor    {@link #MOTOR_LEFT} or {@link #MOTOR_RIGHT}
     * @param backward true for the droid's backward direction (wire direction bit 0x80)
     * @param speed    0..255; the droid only uses the high nibble and will not move below 0x60
     * @param rampMs   time for the droid to ramp to the new speed
     * @return true if the droid's BLE stack acknowledged the write
     */
    boolean sendMotor(int motor, boolean backward, int speed, int rampMs);

    /** Head speed used by {@link #rotateHead}. */
    int HEAD_SPEED = 0xa0;
    /** How long {@link #rotateHead} turns the head. */
    int HEAD_ROTATE_MS = 1500;

    /**
     * Turn the head at {@link #HEAD_SPEED} for {@link #HEAD_ROTATE_MS}, then stop it (libastromech's
     * {@code rotateHead(direction, 0xa0)} followed by a 1.5 s wait and a stop). May block for that time.
     *
     * @param right true for the droid's right (direction bit 0x80), false for left
     * @return true if the droid's BLE stack acknowledged the writes
     */
    boolean rotateHead(boolean right);

    /**
     * Return the head to center and stop there (libastromech's {@code centerHead(speed, true)}).
     *
     * @return true if the droid's BLE stack acknowledged the write
     */
    boolean centerHead();

    /**
     * Play one of the droid's personality sounds and wait for it to finish (the controller's
     * {@code beep} command with {@code wait}). May block for the length of the clip.
     *
     * @param sound index into the droid's personality sounds
     * @return true if the droid's BLE stack acknowledged the write
     */
    boolean sendBeep(int sound);
}
