from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

router = APIRouter()


class SubmitRequest(BaseModel):
    firmware_path: str
    brand: str
    profile: str = "fast"


@router.post("")
async def submit_run(req: SubmitRequest, request: Request):
    fw = Path(req.firmware_path)
    if not fw.exists():
        raise HTTPException(404, f"Firmware not found: {fw}")
    rm = request.app.state.run_manager
    run_id = await rm.submit(fw, req.brand, req.profile)
    return {"run_id": run_id}


@router.get("")
def list_runs(request: Request):
    rm = request.app.state.run_manager
    return {"runs": [r.to_dict() for r in rm.get_all()]}


@router.get("/{run_id}")
def get_run(run_id: str, request: Request):
    rm = request.app.state.run_manager
    state = rm.get(run_id)
    if not state:
        raise HTTPException(404, "Run not found")
    return state.to_dict()


@router.websocket("/{run_id}/ws")
async def run_ws(run_id: str, websocket: WebSocket):
    rm = websocket.app.state.run_manager
    await websocket.accept()

    state = rm.get(run_id)
    if state and state.status in ("success", "failed", "emulation_failed"):
        # Already complete — send final state and close
        await websocket.send_json({"type": "status", "status": state.status, "state": state.to_dict()})
        await websocket.send_json({"type": "done"})
        return

    q = rm.subscribe(run_id)
    try:
        while True:
            event = await asyncio.wait_for(q.get(), timeout=300)
            await websocket.send_json(event)
            if event.get("type") == "done":
                break
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        rm.unsubscribe(run_id, q)


import asyncio  # noqa: E402 — imported here to avoid circular at module level
