package robotics;

import com.qualcomm.robotcore.hardware.DcMotor;
import com.qualcomm.robotcore.hardware.HardwareMap;
import org.firstinspires.ftc.robotcore.external.Telemetry;

/**
 * The FTC StarterBot as a {@link Robot}: a straight passthrough to the FTC SDK.
 *
 * This file is NOT part of the API jar (the API build has no FTC SDK on its classpath). Copy it, or
 * add this directory as a source set, in the FTC TeamCode build. The robot configuration must name
 * the drive motors "left_drive" and "right_drive", as in BioBuzzStarterbotTeleop.
 *
 * Nothing is configured here: directions, zero-power behaviour and power are whatever the program
 * sets, exactly as in a plain OpMode. (The StarterBot program is expected to call
 * {@code rightDrive().setDirection(REVERSE)}.)
 */
public class StarterBotRobot implements Robot {
    private final Telemetry telemetry;
    private final FtcDriveMotor leftDrive;
    private final FtcDriveMotor rightDrive;

    public StarterBotRobot(HardwareMap hardwareMap, Telemetry telemetry) {
        this.telemetry = telemetry;
        this.leftDrive = new FtcDriveMotor(hardwareMap.get(DcMotor.class, "left_drive"));
        this.rightDrive = new FtcDriveMotor(hardwareMap.get(DcMotor.class, "right_drive"));
    }

    @Override public void log(String message) {
        telemetry.addLine(message);
        telemetry.update();
    }

    @Override public DriveMotor leftDrive() { return leftDrive; }

    @Override public DriveMotor rightDrive() { return rightDrive; }

    /** One-to-one adapter onto an SDK motor. */
    private static final class FtcDriveMotor implements DriveMotor {
        private final DcMotor motor;

        FtcDriveMotor(DcMotor motor) { this.motor = motor; }

        @Override public void setPower(double power) { motor.setPower(power); }

        @Override public double getPower() { return motor.getPower(); }

        @Override public void setDirection(Direction d) {
            motor.setDirection(d == Direction.REVERSE ? DcMotor.Direction.REVERSE : DcMotor.Direction.FORWARD);
        }

        @Override public Direction getDirection() {
            return motor.getDirection() == DcMotor.Direction.REVERSE ? Direction.REVERSE : Direction.FORWARD;
        }

        @Override public void setZeroPowerBehavior(ZeroPowerBehavior b) {
            switch (b) {
                case BRAKE: motor.setZeroPowerBehavior(DcMotor.ZeroPowerBehavior.BRAKE); break;
                case FLOAT: motor.setZeroPowerBehavior(DcMotor.ZeroPowerBehavior.FLOAT); break;
                default: motor.setZeroPowerBehavior(DcMotor.ZeroPowerBehavior.UNKNOWN); break;
            }
        }

        @Override public ZeroPowerBehavior getZeroPowerBehavior() {
            switch (motor.getZeroPowerBehavior()) {
                case BRAKE: return ZeroPowerBehavior.BRAKE;
                case FLOAT: return ZeroPowerBehavior.FLOAT;
                default: return ZeroPowerBehavior.UNKNOWN;
            }
        }
    }
}
