package robotics;

import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** A Robot that records what a program does. Used by Test. */
public class MockRobot implements Robot {
    private final List<String> messages = new ArrayList<String>();

    @Override
    public synchronized void log(String message) {
        messages.add(message);
        appendToLogFile(message);
    }

    /**
     * If the harness set -Drobotics.logFile=PATH, also append each message there (one per line) so the
     * server can show the student what their program logged. Failures here never affect the program.
     */
    private static void appendToLogFile(String message) {
        String path = System.getProperty("robotics.logFile");
        if (path == null || path.isEmpty()) return;
        try (Writer w = new OutputStreamWriter(new FileOutputStream(path, true), "UTF-8")) {
            w.write(String.valueOf(message));
            w.write("\n");
        } catch (IOException e) {
            // ignore: logging is best-effort
        }
    }

    /** A snapshot of the messages logged so far, in order. */
    public synchronized List<String> messages() {
        return Collections.unmodifiableList(new ArrayList<String>(messages));
    }
}
