"""MeetBrief AI backend entry point.

Run:  python -m backend.main          (or: uvicorn backend.main:app --port 8000)
Docs: http://127.0.0.1:8000/docs      Web app: http://127.0.0.1:8000/app/
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend import auth
from backend.api.rooms import router as rooms_router
from backend.api.routes import router
from backend.config import ROOT_DIR, settings
from backend.database.db import get_db
from backend.hf import models as hf

log = logging.getLogger("meetbrief")
SIDEPANEL_DIR = ROOT_DIR / "chrome-extension" / "sidepanel"
OPEN_PATHS = {"/api/health", "/api/privacy", "/docs", "/openapi.json", "/", "/favicon.ico"}


async def _retention_loop():
    while True:
        try:
            n = get_db().purge_expired()
            if n:
                log.info("Retention purge removed %d meetings", n)
        except Exception as exc:  # pragma: no cover
            log.warning("Retention purge failed: %s", exc)
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    token = settings.api_token()
    st = hf.status()
    print("\n=== MeetBrief AI backend ===")
    print(f"API:      http://{settings.host}:{settings.port}/api  (docs at /docs)")
    print(f"Web app:  http://{settings.host}:{settings.port}/app/")
    if settings.auth_enabled:
        if settings.host in ("127.0.0.1", "localhost", "::1"):
            print(f"API token (paste into the extension's Settings): {token}")
            print(f"          stored at {settings.token_path}")
        else:
            # reachable from other machines: don't put the owner's full-access token on screen for others to copy
            print(f"API token: stored at {settings.token_path} (copy it with: pbcopy < {settings.token_path})")
            print("          Only YOUR extension needs it. Room members just set their name in Settings → Account.")
    if st["enabled"]:
        ready = [t for t, v in st["tasks"].items() if v["downloaded"]]
        print(f"Models:   Hugging Face (local, {st['device']}); downloaded: {', '.join(ready) or 'none'}")
        if len(ready) < len(st["tasks"]):
            print("          missing models download on first use, or run: python -m backend.hf.download")
    else:
        print(f"Models:   off — {st['reason']}")
    print()
    task = asyncio.create_task(_retention_loop())
    yield
    task.cancel()


app = FastAPI(title="MeetBrief AI", version="1.0.0", lifespan=lifespan,
              description="Multilingual, context-aware meeting assistant backend.")

app.add_middleware(
    CORSMiddleware,
    # extension pages + this server's own web app; members on other machines use the extension
    allow_origin_regex=r"^(chrome-extension://[a-p]{32}|http://(127\.0\.0\.1|localhost)(:\d+)?)$",
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-MeetBrief-Token", "Authorization", "X-MeetBrief-Dev-User"],
    allow_credentials=False,
)


@app.middleware("http")
async def auth_and_headers(request: Request, call_next):
    path = request.url.path
    token_ctx = None
    if path.startswith("/api/") and path not in OPEN_PATHS and request.method != "OPTIONS":
        principal = auth.resolve(request.headers)
        if principal is None:
            return JSONResponse({"detail": "Sign in required: missing or invalid X-MeetBrief-Token / Google sign-in"},
                                status_code=401)
        if not principal.admin and not auth.member_route_allowed(request.method, path):
            return JSONResponse({"detail": "Not available to room members"}, status_code=403)
        token_ctx = auth.current.set(principal)
    try:
        response = await call_next(request)
    finally:
        if token_ctx is not None:
            auth.current.reset(token_ctx)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if path.startswith("/app"):
        # Every directive explicit (missing ones count as wildcards). The only inline script is the injected
        # config, allowed by a per-request nonce; no 'unsafe-inline' for scripts or styles.
        nonce = getattr(request.state, "csp_nonce", None)
        script_src = f"'self' 'nonce-{nonce}'" if nonce else "'self'"
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; script-src {script_src}; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'self'; "
            "form-action 'self'; frame-ancestors 'none'")
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif path.startswith("/app"):
        response.headers["Cache-Control"] = "no-cache"  # always revalidate, so UI updates show up immediately
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Never leak stack traces or library error text to clients; details go to the server log only."""
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Internal error"}, status_code=500)


app.include_router(router)
app.include_router(rooms_router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/app/")


@app.get("/app/", include_in_schema=False)
@app.get("/app/index.html", include_in_schema=False)
def web_app(request: Request):
    """Serve the side-panel UI as a standalone web app (transcript-upload mode).

    The page is same-origin with the API, so the local token is injected here;
    other origins cannot read this response (no CORS grant for them).
    """
    html = (SIDEPANEL_DIR / "index.html").read_text(encoding="utf-8")
    config = json.dumps({"apiBase": "", "token": settings.api_token() if settings.auth_enabled else "", "standalone": True})
    html = html.replace('<script src="../lib/identity.js"></script>', "")  # extension-only (Google sign-in)
    nonce = secrets.token_urlsafe(16)
    request.state.csp_nonce = nonce
    config = config.replace("<", "\\u003c")  # cannot break out of the script element
    html = html.replace("<!--MEETBRIEF_CONFIG-->", f'<script nonce="{nonce}">window.MEETBRIEF_CONFIG = {config};</script>')
    # cache-bust static assets with their modification time so UI updates always load
    for asset in ("api.js", "app.js", "styles.css"):
        version = int((SIDEPANEL_DIR / asset).stat().st_mtime)
        html = html.replace(f'"{asset}"', f'"{asset}?v={version}"')
    return HTMLResponse(html)


app.mount("/app", StaticFiles(directory=SIDEPANEL_DIR), name="app")


def run() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
