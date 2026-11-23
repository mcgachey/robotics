"""Parse javac output into structured diagnostics with beginner-friendly messages."""
import re

_HEAD = re.compile(r"^(?P<file>[^\n:]+\.java):(?P<line>\d+): (?P<sev>error|warning): (?P<msg>.*)$")
_SUMMARY = re.compile(r"^\d+ (errors?|warnings?)$")


def _friendly(msg: str, detail: list[str]) -> str | None:
    """Plain-language rewrites for the handful of errors beginners hit most. None = keep javac's text."""
    m = msg.strip()
    if m.endswith("expected") and m.startswith("';'"):
        return ("A semicolon (;) is missing. Java needs one at the end of each statement. "
                "Look at the end of this line, or the line above it.")
    if m.startswith("reached end of file while parsing"):
        return "The file ended too early. A closing brace } is probably missing. Count your { and }."
    if m.startswith("class, interface, enum, or record expected") or m.startswith("class, interface, or enum expected"):
        return "There is a stray or extra closing brace } (or code outside the class). Check your braces."
    if m.startswith("cannot find symbol"):
        sym = next((d.strip() for d in detail if d.strip().startswith("symbol:")), "")
        name = sym.split(":", 1)[1].strip() if sym else ""
        what = f"Java doesn't know the name \"{name}\"." if name else "Java doesn't know a name used here."
        return what + " Check the spelling and capital letters, and that it is declared before you use it."
    if m.startswith("incompatible types"):
        return "These types don't match: " + m.split(":", 1)[-1].strip() + "."
    if m.startswith("missing return statement"):
        return "This method must return a value on every path, but one path has no return."
    if m.startswith("not a statement"):
        return "This line isn't a complete instruction. Did you forget a call like ( ) or an = ?"
    if "is not abstract and does not override abstract method" in m:
        return "Your class promises to do something (it implements an interface) but is missing a required method. " + m
    return None


def parse_javac(output: str) -> list[dict]:
    """Return [{file, line, column, severity, message, raw}] in output order."""
    lines = output.splitlines()
    diags: list[dict] = []
    i = 0
    while i < len(lines):
        m = _HEAD.match(lines[i])
        if not m:
            i += 1
            continue
        block = [lines[i]]
        i += 1
        while i < len(lines) and not _HEAD.match(lines[i]) and not _SUMMARY.match(lines[i]):
            block.append(lines[i])
            i += 1
        column = 1
        for bl in block[1:]:
            if bl.strip() == "^" or (bl.strip().startswith("^") and set(bl.strip()) <= {"^"}):
                column = bl.index("^") + 1
                break
        detail = block[1:]
        raw = "\n".join(block).rstrip()
        msg = m["msg"].strip()
        diags.append({
            "file": m["file"].rsplit("/", 1)[-1],
            "line": int(m["line"]),
            "column": column,
            "severity": m["sev"],
            "message": _friendly(msg, detail) or msg,
            "javac": msg,
            "raw": raw,
        })
    return diags
