package robotics;

/**
 * The wire to a droid, as seen by {@link DroidRobot}. One method per ESP32 firmware primitive.
 *
 * The real implementation (Pi to ESP32 transport) is not written yet; it forwards to
 * libastromech's {@code Astromech::sendMotor(direction, motor, speed, ramp_ms)}. Tests use a fake.
 *
 * Implementations may block (the BLE write can take a while and retries internally), so
 * {@link DroidRobot} only calls this from its own sender thread, never from student code.
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
}
