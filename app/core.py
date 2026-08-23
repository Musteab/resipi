"""Transport-independent request dispatch.

Both the local stdlib server and the Vercel WSGI entrypoint call `dispatch()`,
so there is exactly one routing/session/static implementation to reason about.
"""
import json
import os
import re
import secrets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "app", "static")

CTYPES = {"html": "text/html", "js": "text/javascript", "css": "text/css", "json": "application/json"}
SID_RX = re.compile(r"[0-9a-f]{16}")


def session_from_cookie(cookie_header):
    """One namespace per browser so concurrent visitors never share demo state."""
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == "resipi_sid" and v and SID_RX.fullmatch(v):
            return v, False
    return secrets.token_hex(8), True


def _json(status, obj, cookie=None):
    headers = [("Content-Type", "application/json; charset=utf-8")]
    if cookie:
        headers.append(("Set-Cookie", cookie))
    return status, headers, json.dumps(obj, ensure_ascii=False).encode()


def dispatch(method, path, body_bytes, cookie_header):
    """-> (status:int, headers:list[(k,v)], body:bytes)"""
    from app.server import ROUTES  # imported late: ROUTES pulls in engine/hermes

    ns, is_new = session_from_cookie(cookie_header)
    cookie = ("resipi_sid=%s; Path=/; Max-Age=86400; SameSite=Lax; Secure" % ns) if is_new else None

    if path in ROUTES:
        try:
            body = json.loads(body_bytes or b"{}") if method == "POST" else {}
        except Exception:
            body = {}
        try:
            return _json(200, ROUTES[path](body, ns), cookie)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _json(500, {"error": "%s: %s" % (type(e).__name__, e)}, cookie)

    # static
    rel = "index.html" if path == "/" else path.lstrip("/")
    fp = os.path.normpath(os.path.join(STATIC, rel))
    if not fp.startswith(STATIC) or not os.path.isfile(fp):
        return _json(404, {"error": "not found"}, cookie)
    ctype = CTYPES.get(fp.rsplit(".", 1)[-1], "text/plain") + "; charset=utf-8"
    headers = [("Content-Type", ctype)]
    if cookie:
        headers.append(("Set-Cookie", cookie))
    with open(fp, "rb") as f:
        return 200, headers, f.read()
