"""Run a child process under limits: wall-clock timeout, bounded output, whole-tree kill."""
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class ProcResult:
    returncode: int | None
    output: str
    timed_out: bool = False
    output_exceeded: bool = False
    cancelled: bool = False
    elapsed_ms: int = 0

    @property
    def killed(self) -> bool:
        return self.timed_out or self.output_exceeded or self.cancelled


def kill_group(proc: subprocess.Popen) -> None:
    """SIGKILL the child's whole process group (it was started in its own session)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # pgid == pid because of start_new_session
    except (ProcessLookupError, PermissionError):
        pass


def run_limited(cmd: list[str], cwd, timeout_sec: float, max_output_bytes: int,
                cancel: threading.Event | None = None,
                on_output: Callable[[str], None] | None = None,
                env: dict | None = None) -> ProcResult:
    """stdout and stderr are merged. Output beyond max_output_bytes kills the process group."""
    start = time.monotonic()
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True, close_fds=True,
    )
    chunks: list[bytes] = []
    state = {"total": 0, "exceeded": False}
    decoder_tail = [b""]

    def reader():
        fd = proc.stdout.fileno()
        while True:
            try:
                data = os.read(fd, 8192)
            except OSError:
                break
            if not data:
                break
            room = max_output_bytes - state["total"]
            if len(data) > room:
                data = data[:max(room, 0)]
                state["exceeded"] = True
            if data:
                chunks.append(data)
                state["total"] += len(data)
                if on_output:
                    buf = decoder_tail[0] + data
                    try:
                        text = buf.decode("utf-8")
                        decoder_tail[0] = b""
                    except UnicodeDecodeError as e:
                        # split mid-character: keep the incomplete tail for the next chunk
                        if e.start >= len(buf) - 3 and e.reason == "unexpected end of data":
                            text = buf[:e.start].decode("utf-8", "replace")
                            decoder_tail[0] = buf[e.start:]
                        else:
                            text = buf.decode("utf-8", "replace")
                            decoder_tail[0] = b""
                    if text:
                        on_output(text)
            if state["exceeded"]:
                break

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    timed_out = cancelled = False
    deadline = start + timeout_sec
    try:
        while True:
            if proc.poll() is not None and not t.is_alive():
                break
            if state["exceeded"]:
                break
            if cancel is not None and cancel.is_set():
                cancelled = True
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            if proc.poll() is not None:
                # exited, but a grandchild may still hold the pipe open: give the reader a moment
                t.join(0.2)
                if t.is_alive():
                    break
                continue
            t.join(0.02)
    finally:
        # Always take the whole group down, including stray grandchildren, then reap.
        kill_group(proc)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            pass
        t.join(2)
        try:
            proc.stdout.close()
        except OSError:
            pass
    out = b"".join(chunks).decode("utf-8", "replace")
    return ProcResult(
        returncode=proc.returncode, output=out, timed_out=timed_out,
        output_exceeded=state["exceeded"], cancelled=cancelled,
        elapsed_ms=int((time.monotonic() - start) * 1000),
    )
