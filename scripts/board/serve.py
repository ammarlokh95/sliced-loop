#!/usr/bin/env python3
"""Kanban board for this project's tasks.

The board is part of the plugin, not the project: it is served from the plugin
install and writes nothing into the repository except the task files a drag
edits. Should it ever need to persist anything of its own — a cached render, a
per-viewer preference — that belongs in `tasklib.state_dir()`, which is
gitignored, so nothing the board produces is ever committed.

Serves a drag-and-drop board over localhost and writes status changes straight
back into the task files. Moving a card is a manual override: it edits the
`status:` and `updated:` frontmatter fields and appends a line to `## Thread`
recording that a human moved it, so the agents can see what happened.

    python3 sliced-loop board [--port 7777] [--no-open]

Standard library only. Binds to 127.0.0.1.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BOARD_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BOARD_DIR.parent))
import tasklib  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    server_version = "taskboard"

    def log_message(self, fmt, *args):  # quieter console
        if args and "POST" in str(args[0]):
            super().log_message(fmt, *args)

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: object) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route in ("/", "/index.html"):
            return self._send(200, (BOARD_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        if route == "/api/tasks":
            return self._json(200, {
                "statuses": tasklib.STATUSES,
                "tasks": tasklib.load_tasks(),
            })
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/move":
            return self._json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = tasklib.move_task(
                str(payload.get("id", "")),
                str(payload.get("status", "")),
            )
        except (ValueError, OSError) as exc:
            return self._json(400, {"ok": False, "error": str(exc)})
        self._json(200 if result.get("ok") else 400, result)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=7777)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = ap.parse_args()

    url = f"http://127.0.0.1:{args.port}/"
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as httpd:
        print(f"task board  →  {url}")
        print(f"tasks from  →  {tasklib.tasks_dir()}")
        print("ctrl-c to stop")
        if not args.no_open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
