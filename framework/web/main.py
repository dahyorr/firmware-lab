"""
FirmScan web server.

Usage:
    cd ~/project/framework
    .venv/bin/uvicorn web.main:app --host 0.0.0.0 --port 8000

Build the frontend first:
    cd web/frontend && npm install && npm run build
"""

import base64
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from web.run_manager import RunManager
from web.routers import firmware, reports, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    rm = RunManager()
    app.state.run_manager = rm
    await rm.start()
    yield


app = FastAPI(title="FirmScan", lifespan=lifespan)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """
    Shared-credential HTTP Basic Auth for the whole app (API + static SPA).

    Credentials come from FIRMSCAN_AUTH_USER / FIRMSCAN_AUTH_PASS so the same
    generated pair can be exported identically across every deployed
    instance without committing secrets to source. If either env var is
    unset, auth is disabled (local dev convenience) - every deployed
    instance must set both.
    """

    def __init__(self, app):
        super().__init__(app)
        self.user = os.environ.get("FIRMSCAN_AUTH_USER")
        self.password = os.environ.get("FIRMSCAN_AUTH_PASS")

    async def dispatch(self, request: Request, call_next):
        if not self.user or not self.password:
            return await call_next(request)

        challenge = Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="FirmScan"'})

        auth = request.headers.get("authorization")
        if not auth or not auth.lower().startswith("basic "):
            return challenge
        try:
            decoded = base64.b64decode(auth.split(" ", 1)[1]).decode()
            given_user, given_pass = decoded.split(":", 1)
        except Exception:
            return challenge

        if not (secrets.compare_digest(given_user, self.user)
                and secrets.compare_digest(given_pass, self.password)):
            return challenge

        return await call_next(request)


app.add_middleware(BasicAuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(firmware.router, prefix="/api/firmware", tags=["firmware"])
app.include_router(runs.router,     prefix="/api/runs",     tags=["runs"])
app.include_router(reports.router,  prefix="/api/reports",  tags=["reports"])

_dist = Path(__file__).parent / "frontend" / "dist"

if _dist.exists():
    # Serve static assets (JS, CSS, images) directly.
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    # SPA catch-all: serve index.html for all non-API paths so that
    # React Router can handle client-side navigation to /reports, /run/:id, etc.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_index(request: Request, full_path: str):
        index = _dist / "index.html"
        return FileResponse(str(index))
