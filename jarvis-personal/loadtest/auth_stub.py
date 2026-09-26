"""Local stand-in for Supabase Auth's GET /auth/v1/user (load tests only).

Tokens are "loadtest-<n>"; each maps to a synthetic Google identity
loadtest-<n>@example.test with a stable id. No real identity is involved.
Optional AUTH_STUB_DELAY_MS adds latency to model the real network call.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DELAY = float(os.getenv("AUTH_STUB_DELAY_MS", "0")) / 1000


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if self.path != "/auth/v1/user" or not token.startswith("loadtest-"):
            self.send_response(401)
            self.end_headers()
            return
        time.sleep(DELAY)
        n = token.removeprefix("loadtest-")
        body = json.dumps({
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"dincr-loadtest:{n}")),
            "email": f"loadtest-{n}@example.test",
            "app_metadata": {"provider": "google", "providers": ["google"]},
            "user_metadata": {},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    # A burst of concurrent sign-ins must queue, not be refused (the default backlog is 5).
    ThreadingHTTPServer.request_queue_size = 256
    ThreadingHTTPServer(("127.0.0.1", int(os.getenv("AUTH_STUB_PORT", "8791"))), Handler).serve_forever()
