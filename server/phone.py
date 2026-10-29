import hashlib
import os
import secrets
import socket
import time
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from core import db

COOKIE = "kh_session"
PAIR_CODE_SECONDS = 300
SESSION_DAYS = 365
STATIC = Path(__file__).parent / "static"
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

router = APIRouter()
_pair_codes = {}


def _hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def valid_session(raw):
    if not raw:
        return False
    with closing(db.connect()) as conn:
        return conn.execute("SELECT 1 FROM phone_sessions WHERE token_hash = ?", (_hash(raw),)).fetchone() is not None


def _lan_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def _message_page(title, body, status=200):
    html = (STATIC / "message.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("{title}", title).replace("{body}", body), status, headers=SECURITY_HEADERS)


@router.post("/api/pair")
def start_pairing(request: Request):
    now = time.monotonic()
    for code, expires in list(_pair_codes.items()):
        if expires < now:
            del _pair_codes[code]
    code = secrets.token_urlsafe(16)
    _pair_codes[code] = now + PAIR_CODE_SECONDS
    base = os.environ.get("KITCHEN_PUBLIC_URL") or f"http://{_lan_ip()}:{request.url.port or 8000}"
    return {"url": f"{base.rstrip('/')}/pair?code={code}", "expires_in": PAIR_CODE_SECONDS}


@router.post("/api/phones/revoke-all")
def revoke_all_phones():
    with closing(db.connect()) as conn, conn:
        return {"revoked": conn.execute("DELETE FROM phone_sessions").rowcount}


@router.get("/pair")
def finish_pairing(code: str = ""):
    expires = _pair_codes.pop(code, None)
    if expires is None or expires < time.monotonic():
        return _message_page("Code expired", "On the kitchen screen, tap <b>Phone</b> to get a new code.", 400)
    raw = secrets.token_urlsafe(32)
    with closing(db.connect()) as conn, conn:
        conn.execute("INSERT INTO phone_sessions (token_hash) VALUES (?)", (_hash(raw),))
    response = RedirectResponse("/m", status_code=303)
    response.set_cookie(COOKIE, raw, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax")
    return response


@router.get("/m")
def mobile_page(request: Request):
    if not valid_session(request.cookies.get(COOKIE)):
        return _message_page("Not connected", "On the kitchen screen, tap <b>Phone</b> and scan the code.", 401)
    return FileResponse(STATIC / "mobile.html", headers=SECURITY_HEADERS)


@router.get("/m/app.js")
def mobile_script():
    return FileResponse(STATIC / "mobile.js", media_type="text/javascript", headers=SECURITY_HEADERS)
