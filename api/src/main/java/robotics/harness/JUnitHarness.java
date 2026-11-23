package robotics.harness;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.util.ArrayList;
import java.util.List;
import org.junit.runner.Description;
import org.junit.runner.JUnitCore;
import org.junit.runner.Request;
import org.junit.runner.notification.Failure;
import org.junit.runner.notification.RunListener;

/**
 * Runs JUnit 4 test classes and writes structured results as JSON: [{"name","status","message"}].
 * Student System.out stays on stdout; results go to a file so the two never mix.
 *
 * Usage: java -cp ... robotics.harness.JUnitHarness results.json TestClass...
 */
public final class JUnitHarness {
    private static final class Rec {
        String name;
        String status = "passed";
        String message = "";
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("usage: JUnitHarness <results.json> <TestClass>...");
            System.exit(2);
        }
        final List<Rec> recs = new ArrayList<Rec>();
        final Rec[] current = new Rec[1];
        JUnitCore core = new JUnitCore();
        core.addListener(new RunListener() {
            @Override public void testStarted(Description d) {
                Rec r = new Rec();
                r.name = d.getMethodName() != null ? d.getMethodName() : d.getDisplayName();
                current[0] = r;
                recs.add(r);
            }
            @Override public void testFailure(Failure f) {
                Rec r = current[0];
                if (r == null) { // failure outside a test (class setup)
                    r = new Rec();
                    r.name = f.getDescription().getDisplayName();
                    recs.add(r);
                }
                Throwable t = f.getException();
                r.status = (t instanceof AssertionError) ? "failed" : "error";
                r.message = describe(t);
            }
            @Override public void testAssumptionFailure(Failure f) {
                if (current[0] != null) { current[0].status = "skipped"; current[0].message = String.valueOf(f.getMessage()); }
            }
            @Override public void testIgnored(Description d) {
                Rec r = new Rec();
                r.name = d.getMethodName() != null ? d.getMethodName() : d.getDisplayName();
                r.status = "skipped";
                recs.add(r);
            }
        });
        for (int i = 1; i < args.length; i++) {
            core.run(Request.aClass(Class.forName(args[i])));
        }
        System.out.flush();
        System.err.flush();
        Writer w = new OutputStreamWriter(new FileOutputStream(new File(args[0])), "UTF-8");
        try {
            w.write("[");
            for (int i = 0; i < recs.size(); i++) {
                Rec r = recs.get(i);
                if (i > 0) w.write(",");
                w.write("{\"name\":" + quote(r.name) + ",\"status\":" + quote(r.status)
                        + ",\"message\":" + quote(r.message) + "}");
            }
            w.write("]");
        } finally {
            w.close();
        }
    }

    private static String describe(Throwable t) {
        if (t instanceof AssertionError) {
            String m = t.getMessage();
            return (m == null || m.isEmpty()) ? "The test's check did not hold (assertion failed)." : m;
        }
        StringBuilder sb = new StringBuilder(t.toString());
        for (StackTraceElement e : t.getStackTrace()) {
            String c = e.getClassName();
            if (!c.startsWith("org.junit.") && !c.startsWith("java.") && !c.startsWith("sun.")
                    && !c.startsWith("jdk.") && !c.startsWith("robotics.harness.")) {
                sb.append("\n    at ").append(e);
                break;
            }
        }
        return sb.toString();
    }

    private static String quote(String s) {
        StringBuilder sb = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c)); else sb.append(c);
            }
        }
        return sb.append('"').toString();
    }

    private JUnitHarness() {}
}
