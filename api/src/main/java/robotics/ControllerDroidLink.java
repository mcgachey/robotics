package robotics;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.Charset;
import java.util.function.Consumer;

/**
 * {@link DroidLink} over the Pi's board controller (astromech_server raspberrypi_controller), which
 * owns the USB serial port to the droid's ESP32 board: one HTTP POST per primitive to
 * {@code <baseUrl>/api/boards/<boardId>/commands/<cmd>}. Only works from the Pi itself, because
 * the controller accepts motor commands from loopback clients only.
 *
 * Failures (board unplugged, droid asleep, controller down) return false so that
 * {@link DroidRobot} logs and retries. A reply that will never succeed (4xx) is also reported to the
 * logger, once per distinct message.
 */
public final class ControllerDroidLink implements DroidLink {
    private static final Charset UTF8 = Charset.forName("UTF-8");
    private static final int CONNECT_TIMEOUT_MS = 3000;
    /** A head turn blocks the controller for 1.5 s, and a BLE write can retry for several seconds. */
    private static final int READ_TIMEOUT_MS = 20000;

    private final String commandsUrl;
    private final Consumer<String> logger;
    private String lastProblem = "";

    public ControllerDroidLink(String baseUrl, String boardId, Consumer<String> logger) {
        if (boardId == null || !boardId.matches("[A-Za-z0-9_.-]+")) throw new IllegalArgumentException("boardId");
        String base = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.commandsUrl = base + "/api/boards/" + boardId + "/commands/";
        this.logger = logger;
    }

    @Override public boolean sendMotor(int motor, boolean backward, int speed, int rampMs) {
        return post("motor", "{\"motor\":\"" + (motor == MOTOR_LEFT ? "left" : "right") + "\",\"backward\":"
                + backward + ",\"speed\":" + speed + ",\"ramp_ms\":" + rampMs + "}");
    }

    @Override public boolean rotateHead(boolean right) {
        return post("rotate_head", "{\"direction\":\"" + (right ? "right" : "left") + "\"}");
    }

    @Override public boolean centerHead() {
        return post("center_head", "{}");
    }

    @Override public boolean sendBeep(int sound) {
        return post("beep", "{\"sound\":" + sound + ",\"wait\":true}");
    }

    /** Stop both wheels. Used by the harness as a last resort. */
    public boolean stopWheels() {
        return post("stop", "{}");
    }

    private boolean post(String cmd, String json) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(commandsUrl + cmd).openConnection();
            c.setConnectTimeout(CONNECT_TIMEOUT_MS);
            c.setReadTimeout(READ_TIMEOUT_MS);
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            byte[] body = json.getBytes(UTF8);
            c.setFixedLengthStreamingMode(body.length);
            OutputStream out = c.getOutputStream();
            try { out.write(body); } finally { out.close(); }
            int status = c.getResponseCode();
            if (status / 100 == 2) {
                drain(c.getInputStream());
                lastProblem = "";
                return true;
            }
            String reply = drain(c.getErrorStream());
            problem(cmd + " refused (HTTP " + status + "): " + reply);
            return false;
        } catch (IOException e) {
            problem(cmd + " failed: " + e);
            return false;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private void problem(String message) {
        if (!message.equals(lastProblem)) {
            lastProblem = message;
            logger.accept("droid link: " + message);
        }
    }

    private static String drain(InputStream in) throws IOException {
        if (in == null) return "";
        try {
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            byte[] chunk = new byte[1024];
            int n;
            while ((n = in.read(chunk)) > 0 && buf.size() < 4096) buf.write(chunk, 0, n);
            return new String(buf.toByteArray(), UTF8).trim();
        } finally {
            in.close();
        }
    }
}
