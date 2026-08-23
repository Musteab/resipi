"""Vercel serverless entrypoint (file-based /api function).

Delegates to app.core.dispatch so serverless and the local stdlib server run
identical routing, session and static logic.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RESIPI_DB", "/tmp/resipi.db")
os.environ.setdefault("RESIPI_BUNDLE_DIR", "/tmp/bundles")

from app.core import dispatch  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _serve(self):
        n = int(self.headers.get("Content-Length") or 0)
        body_in = self.rfile.read(n) if n else b""
        status, headers, body = dispatch(
            self.command, urlparse(self.path).path, body_in, self.headers.get("Cookie", ""))
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _serve
    do_POST = _serve
