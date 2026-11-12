"""The local picker: one page on 127.0.0.1 where the founder plays each choice and clicks one. It serves until the
click or the time limit, then stops; nothing leaves this machine. Used by `kit.py pick`."""

from __future__ import annotations

import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import kit_core

AUDIO_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg"}


def make_server(title: str, choices: list, port: int = 0):
    """(server, picked): the page's server on 127.0.0.1 and the list its pick lands in."""
    page = kit_core.picker_html(title, choices).encode("utf-8")
    picked: list = []
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(body)

        def _index(self, prefix: str):
            tail = self.path[len(prefix):] if self.path.startswith(prefix) else ""
            return int(tail) if tail.isdigit() and int(tail) < len(choices) else None

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self._send(200, page, "text/html; charset=utf-8")
            k = self._index("/audio/")
            if k is None:
                return self._send(404, b"not found", "text/plain")
            path = choices[k]["file"]
            body, kind = path.read_bytes(), AUDIO_TYPES.get(path.suffix.lower(), "application/octet-stream")
            part = kit_core.byte_range(self.headers.get("Range"), len(body))  # Safari plays audio only with ranges
            if part is None:
                return self._send(200, body, kind)
            start, end = part
            self.send_response(206)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(body)}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(body[start:end + 1])

        def do_POST(self):
            k = self._index("/pick/")
            if k is None:
                return self._send(404, b"not found", "text/plain")
            first = not picked
            if first:
                picked.append(choices[k])
            self._send(200, f"Picked {picked[0]['name']}. You can close this tab.".encode("utf-8"), "text/plain; charset=utf-8")
            if first:
                done.set()  # after the reply is written, so the page always shows it

        def log_message(self, *args):  # the kit logs its own lines
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.picked, server.done = picked, done
    return server, picked


def serve(title: str, choices: list, seconds: float, open_browser: bool, log) -> dict | None:
    """Serve the page until a pick or `seconds`; the pick, or None. The server always stops before returning."""
    server, picked = make_server(title, choices)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    thread.start()
    log("pick", f"page open at {url} (a server on this machine only, it stops after the click or {seconds / 60:g} min)")
    try:
        if open_browser:
            webbrowser.open_new_tab(url)
        server.done.wait(seconds)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return picked[0] if picked else None
