package robotics;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Consumer;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;

public class ControllerDroidLinkTest {
    private HttpServer server;
    private final List<String> requests = Collections.synchronizedList(new ArrayList<String>());
    private final List<String> logs = Collections.synchronizedList(new ArrayList<String>());
    private volatile int status = 200;
    private String url;

    @Before public void start() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", new HttpHandler() {
            @Override public void handle(HttpExchange ex) throws IOException {
                InputStream in = ex.getRequestBody();
                ByteArrayOutputStream b = new ByteArrayOutputStream();
                byte[] chunk = new byte[256];
                int n;
                while ((n = in.read(chunk)) > 0) b.write(chunk, 0, n);
                requests.add(ex.getRequestMethod() + " " + ex.getRequestURI().getPath() + " " + b.toString("UTF-8"));
                byte[] reply = status == 200 ? "{}".getBytes("UTF-8") : "{\"error\":\"nope\"}".getBytes("UTF-8");
                ex.sendResponseHeaders(status, reply.length);
                ex.getResponseBody().write(reply);
                ex.close();
            }
        });
        server.start();
        url = "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @After public void stop() { server.stop(0); }

    private ControllerDroidLink link() {
        return new ControllerDroidLink(url + "/", "abc123", new Consumer<String>() {
            @Override public void accept(String s) { logs.add(s); }
        });
    }

    @Test public void sendsEachPrimitiveToTheBoardsCommandEndpoint() {
        ControllerDroidLink l = link();
        assertTrue(l.sendMotor(DroidLink.MOTOR_RIGHT, true, 0x80, 100));
        assertTrue(l.sendMotor(DroidLink.MOTOR_LEFT, false, 0, 300));
        assertTrue(l.rotateHead(true));
        assertTrue(l.rotateHead(false));
        assertTrue(l.centerHead());
        assertTrue(l.sendBeep(4));
        assertTrue(l.stopWheels());
        String base = "POST /api/boards/abc123/commands/";
        assertEquals(java.util.Arrays.asList(
                base + "motor {\"motor\":\"right\",\"backward\":true,\"speed\":128,\"ramp_ms\":100}",
                base + "motor {\"motor\":\"left\",\"backward\":false,\"speed\":0,\"ramp_ms\":300}",
                base + "rotate_head {\"direction\":\"right\"}",
                base + "rotate_head {\"direction\":\"left\"}",
                base + "center_head {}",
                base + "beep {\"sound\":4,\"wait\":true}",
                base + "stop {}"), requests);
    }

    @Test public void failuresReturnFalseAndAreLoggedOncePerMessage() {
        status = 503;
        ControllerDroidLink l = link();
        assertFalse(l.centerHead());
        assertFalse(l.centerHead());
        assertEquals(1, logs.size());
        assertTrue(logs.get(0), logs.get(0).contains("HTTP 503"));
        status = 200;
        assertTrue(l.centerHead());
    }

    @Test public void unreachableControllerReturnsFalse() {
        server.stop(0);
        assertFalse(link().sendBeep(0));
        assertEquals(1, logs.size());
    }

    @Test(expected = IllegalArgumentException.class) public void boardIdIsValidatedBecauseItBecomesAPathSegment() {
        new ControllerDroidLink(url, "../x", new Consumer<String>() { @Override public void accept(String s) { } });
    }
}
