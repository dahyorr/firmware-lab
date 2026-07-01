"""
FirmScan web server.

Usage:
    cd ~/project/framework
    .venv/bin/uvicorn web.main:app --host 0.0.0.0 --port 8000

Build the frontend first:
    cd web/frontend && npm install && npm run build
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.run_manager import RunManager
from web.routers import firmware, reports, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    rm = RunManager()
    app.state.run_manager = rm
    await rm.start()
    yield


app = FastAPI(title="FirmScan", lifespan=lifespan)

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
