"""Vercel entrypoint. Exposes a dependency-free WSGI `app`.

Serverless filesystems are read-only apart from /tmp, so the demo store lives
there. State is per-session and self-healing, so a cold instance still serves a
complete demo (see app/server.py: _ensure_ready).
"""
import os
import sys

os.environ.setdefault("RESIPI_DB", "/tmp/resipi.db")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core import dispatch  # noqa: E402

STATUS = {200: "200 OK", 404: "404 Not Found", 500: "500 Internal Server Error"}


def app(environ, start_response):
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    body_in = environ["wsgi.input"].read(length) if length else b""

    status, headers, body = dispatch(
        environ.get("REQUEST_METHOD", "GET"),
        environ.get("PATH_INFO", "/"),
        body_in,
        environ.get("HTTP_COOKIE", ""),
    )
    headers = list(headers) + [("Content-Length", str(len(body)))]
    start_response(STATUS.get(status, "%d Error" % status), headers)
    return [body]
