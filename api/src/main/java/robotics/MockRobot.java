package robotics;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** A Robot that records what a program does. Used by Test. */
public class MockRobot implements Robot {
    private final List<String> messages = new ArrayList<String>();

    @Override
    public synchronized void log(String message) {
        messages.add(message);
    }

    /** A snapshot of the messages logged so far, in order. */
    public synchronized List<String> messages() {
        return Collections.unmodifiableList(new ArrayList<String>(messages));
    }
}
