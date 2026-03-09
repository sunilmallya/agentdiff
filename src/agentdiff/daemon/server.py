"""HTTP server listening on a Unix domain socket."""

import argparse
import json
import os
import signal
import socket
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path

MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB


class UnixHTTPServer(ThreadingMixIn, HTTPServer):
    """ThreadingHTTPServer bound to a Unix domain socket."""
    address_family = socket.AF_UNIX
    daemon_threads = True
    project_root: str = ""

    def server_bind(self):
        sock_path = self.server_address
        if os.path.exists(sock_path):
            os.unlink(sock_path)
        self.socket.bind(sock_path)
        os.chmod(sock_path, 0o660)


class EventHandler(BaseHTTPRequestHandler):
    """Handles POST /event from hook scripts."""

    def do_POST(self):
        if self.path == "/event":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > MAX_CONTENT_LENGTH:
                self._respond(413, {"error": "payload too large"})
                return
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body)
                from agentdiff.daemon.handlers import handle_event
                handle_event(payload, self.server.project_root)
                self._respond(200, {"ok": True})
            except Exception as e:
                from agentdiff.shared.errors import log_error
                log_error("daemon.handle_event", e, project_root=self.server.project_root)
                self._respond(200, {"ok": True, "degraded": True})
        else:
            self._respond(404, {"error": "not found"})

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok"})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code: int, body: dict):
        try:
            response = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        pass


def run_daemon(project_root: str):
    """Start the daemon. Blocks until shutdown."""
    from agentdiff.shared.paths import get_socket_path, get_pid_path

    sock_path = str(get_socket_path(project_root))
    pid_path = get_pid_path(project_root)

    pid_path.write_text(str(os.getpid()))

    server = UnixHTTPServer(sock_path, EventHandler)
    server.project_root = project_root

    def shutdown_handler(signum, frame):
        # Don't call server.shutdown() from signal handler — it deadlocks.
        # Set the internal flag and let serve_forever() exit naturally.
        server._BaseServer__shutdown_request = True
        # Cleanup in a separate thread to avoid signal handler restrictions
        def cleanup():
            if os.path.exists(sock_path):
                os.unlink(sock_path)
            if pid_path.exists():
                pid_path.unlink()
        threading.Thread(target=cleanup, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    try:
        server.serve_forever()
    finally:
        server.server_close()
        if os.path.exists(sock_path):
            os.unlink(sock_path)
        if pid_path.exists():
            pid_path.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    run_daemon(args.project_root)
