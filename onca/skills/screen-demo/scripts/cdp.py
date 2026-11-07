"""A small Chrome DevTools Protocol client on Python's standard library (a WebSocket per RFC 6455).

The frame codec (`accept_key`, `encode_frame`, `decode_frames`) is pure; `Cdp` holds the one socket.
Chrome is found and started here too, always with its own profile and headless unless asked.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
import record_core  # noqa: E402

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

CHROME_APPS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def accept_key(key: str) -> str:
    """The `Sec-WebSocket-Accept` value a server answers to `key`."""
    return base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()


def encode_frame(payload: bytes, opcode: int = 1, mask: bytes = b"\0\0\0\0") -> bytes:
    """One final, masked client frame (a client must mask every frame)."""
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += bytes([0x80 | 126]) + n.to_bytes(2, "big")
    else:
        head += bytes([0x80 | 127]) + n.to_bytes(8, "big")
    return head + mask + bytes(b ^ mask[k % 4] for k, b in enumerate(payload))


def _frame_at(buf: bytes, i: int):
    """(fin, opcode, payload, next index) of the frame at `i`, or None when it is not all there yet."""
    if len(buf) - i < 2:
        return None
    b0, b1 = buf[i], buf[i + 1]
    n, j = b1 & 0x7F, i + 2
    if n == 126:
        if len(buf) - j < 2:
            return None
        n, j = int.from_bytes(buf[j:j + 2], "big"), j + 2
    elif n == 127:
        if len(buf) - j < 8:
            return None
        n, j = int.from_bytes(buf[j:j + 8], "big"), j + 8
    mask = None
    if b1 & 0x80:
        if len(buf) - j < 4:
            return None
        mask, j = buf[j:j + 4], j + 4
    if len(buf) - j < n:
        return None
    data = buf[j:j + n]
    if mask:
        data = bytes(b ^ mask[k % 4] for k, b in enumerate(data))
    return bool(b0 & 0x80), b0 & 0x0F, data, j + n


def decode_frames(buf: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    """The complete messages in `buf` as (opcode, payload), continuation frames joined, and the bytes left over
    (from the start of a message not complete yet). A control frame (ping, pong, close) inside a fragmented
    message is returned at once and taken out of the bytes left over."""
    out: list[tuple[int, bytes]] = []
    i = consumed = 0
    pending: tuple[int, bytes] | None = None
    while True:
        at = i
        frame = _frame_at(buf, i)
        if frame is None:
            break
        fin, opcode, data, i = frame
        if opcode >= 8:
            out.append((opcode, data))
            if pending is None:
                consumed = i
            else:
                buf = buf[:at] + buf[i:]
                i = at
            continue
        if opcode != 0:
            pending = (opcode, data)
        elif pending is not None:
            pending = (pending[0], pending[1] + data)
        else:
            consumed = i  # a stray continuation: drop it
            continue
        if fin:
            out.append(pending)
            pending = None
            consumed = i
    return out, buf[consumed:]


class Cdp:
    """One DevTools WebSocket: `call` waits for its answer, events queue for `next_event`."""

    def __init__(self, ws_url: str, timeout: float = 30):
        u = urlparse(ws_url)
        self.timeout = timeout
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = u.path + (f"?{u.query}" if u.query else "")
        self.sock.sendall((
            f"GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("DevTools closed the connection during the handshake")
            head += chunk
        head, self.buf = head.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        if " 101 " not in lines[0] + " ":
            raise ConnectionError(f"DevTools refused the WebSocket: {lines[0]}")
        headers = {k.strip().lower(): v.strip() for k, v in (ln.split(":", 1) for ln in lines[1:] if ":" in ln)}
        if headers.get("sec-websocket-accept") != accept_key(key):
            raise ConnectionError("DevTools answered with a wrong Sec-WebSocket-Accept")
        self.next_id = 0
        self.answers: dict[int, dict] = {}
        self.events: list[dict] = []
        self.closed = False

    def _write(self, payload: bytes, opcode: int = 1) -> None:
        self.sock.sendall(encode_frame(payload, opcode, os.urandom(4)))

    def _pump(self, timeout: float) -> bool:
        """Read what arrives within `timeout`; False when nothing did."""
        if self.closed:
            raise ConnectionError("DevTools connection closed")
        self.sock.settimeout(max(0.001, timeout))
        try:
            chunk = self.sock.recv(1 << 20)
        except socket.timeout:
            return False
        if not chunk:
            self.closed = True
            raise ConnectionError("DevTools connection closed")
        frames, self.buf = decode_frames(self.buf + chunk)
        for opcode, data in frames:
            if opcode == 9:
                self._write(data, 10)
            elif opcode == 8:
                self.closed = True
                raise ConnectionError("DevTools connection closed")
            elif opcode == 1:
                msg = json.loads(data)
                if "id" in msg:
                    self.answers[msg["id"]] = msg
                else:
                    self.events.append(msg)
        return True

    def send(self, method: str, **params) -> int:
        self.next_id += 1
        self._write(json.dumps({"id": self.next_id, "method": method, "params": params}).encode())
        return self.next_id

    def call(self, method: str, **params) -> dict:
        mid = self.send(method, **params)
        deadline = time.monotonic() + self.timeout
        while mid not in self.answers:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"{method}: no answer within {self.timeout} s")
            self._pump(left)
        msg = self.answers.pop(mid)
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error'].get('message', msg['error'])}")
        return msg.get("result", {})

    def next_event(self, timeout: float) -> dict | None:
        deadline = time.monotonic() + timeout
        while not self.events:
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            self._pump(left)
        return self.events.pop(0)

    def close(self) -> None:
        if not self.closed:
            try:
                self._write(b"", 8)
            except OSError:
                pass
        self.closed = True
        self.sock.close()


def page_ws_url(port: int) -> str:
    """The WebSocket URL of the first page target of the Chrome on `port`."""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
        targets = json.loads(r.read())
    for t in targets:
        if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
            return t["webSocketDebuggerUrl"]
    raise ConnectionError(f"no page target on port {port}")


def find_chrome() -> str | None:
    """Google Chrome or Chromium: the macOS apps first, then `google-chrome` or `chromium` on PATH."""
    for app in CHROME_APPS:
        p = Path(app).expanduser()
        if p.exists():
            return str(p)
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def launch_chrome(port: int, profile: str, size: tuple[int, int], headed: bool = False, dpr: float = 1) -> subprocess.Popen:
    chrome = find_chrome()
    if not chrome:
        raise FileNotFoundError("no Chrome found: install Google Chrome")
    return subprocess.Popen(record_core.chrome_command(chrome, port, profile, size, headed, dpr),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_for_page(port: int, seconds: float = 20) -> str:
    """`page_ws_url(port)` once Chrome answers, retried for `seconds`."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            return page_ws_url(port)
        except (OSError, ConnectionError, ValueError):
            if time.monotonic() > deadline:
                raise ConnectionError(f"Chrome did not open its debugging port {port} within {seconds} s")
            time.sleep(0.2)


@contextmanager
def chrome(size: tuple[int, int], dpr: float = 1, headed: bool = False, profile: str | None = None):
    """A Chrome of its own (a throwaway profile unless `profile` is given) and a client on its first page; closed,
    and a throwaway profile removed, afterwards. Exits 1 with the reason when Chrome is missing or fails."""
    if not find_chrome():
        print("no Chrome found: install Google Chrome", file=sys.stderr)
        raise SystemExit(1)
    own = profile is None
    profile = profile or tempfile.mkdtemp(prefix="onca-chrome-profile-")
    port = free_port()
    print(f"[screen-demo] Chrome {'headed' if headed else 'headless'}, profile {profile}, port {port}", file=sys.stderr)
    proc = launch_chrome(port, profile, size, headed, dpr)
    client = None
    try:
        client = Cdp(wait_for_page(port))
        yield client
    except (ConnectionError, TimeoutError, RuntimeError) as e:
        print(f"Chrome failed: {e}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        if client:
            client.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if own:
            shutil.rmtree(profile, ignore_errors=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
