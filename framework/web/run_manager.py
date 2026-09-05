"""
Background run queue and WebSocket event fan-out.

Only one FirmAE analysis runs at a time (R-18). Submitted runs queue up
and are dispatched by a single asyncio worker. Each run streams structured
events (publisher events + captured stdout) to any connected WebSocket
subscribers via asyncio.Queue fan-out.
"""

import asyncio
import sys
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Per-run cap on retained events for late-subscriber replay. FirmAE emulation
# emits a few hundred log lines at most; 2000 leaves generous headroom.
_HISTORY_MAX = 2000


@dataclass
class RunState:
    run_id: str
    firmware_name: str
    firmware_path: str
    brand: str
    profile: str
    status: str = "queued"
    queued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    report_path: str | None = None
    services: int = 0
    cves: int = 0
    cred_hits: int = 0
    web_findings: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class _StdoutCapture:
    """
    Captures print() output from the worker thread and forwards each line
    as a {"type": "log", "msg": ...} event via call_soon_threadsafe.
    """
    def __init__(self, emit_fn):
        self._emit = emit_fn
        self._buf = ""

    def write(self, text: str) -> None:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line:
                self._emit({"type": "log", "msg": line})

    def flush(self) -> None:
        pass


class QueuePublisher:
    """
    Drop-in replacement for EventPublisher / NullPublisher that routes events
    to the RunManager's fan-out instead of Valkey. Safe to call from a worker
    thread — uses call_soon_threadsafe to cross the thread boundary.
    """
    def __init__(self, run_id: str, rm: "RunManager", loop: asyncio.AbstractEventLoop):
        self.run_id = run_id
        self._rm = rm
        self._loop = loop

    def _send(self, event: dict) -> None:
        self._loop.call_soon_threadsafe(self._rm._emit, self.run_id, event)

    def start(self, module: str, detail: str = "") -> None:
        self._send({"type": "start", "module": module, "detail": detail})

    def progress(self, module: str, msg: str) -> None:
        self._send({"type": "progress", "module": module, "msg": msg})

    def success(self, module: str, data: dict | None = None) -> None:
        self._send({"type": "success", "module": module, "data": data or {}})

    def failure(self, module: str, error: str) -> None:
        self._send({"type": "failure", "module": module, "error": error})


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}
        self._queue: asyncio.Queue[RunState] | None = None
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._history: dict[str, deque[dict]] = {}
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def start(self) -> None:
        self._queue = asyncio.Queue()
        asyncio.create_task(self._worker())

    async def submit(self, firmware_path: Path, brand: str, profile: str) -> str:
        run_id = uuid.uuid4().hex[:8]
        state = RunState(
            run_id=run_id,
            firmware_name=firmware_path.name,
            firmware_path=str(firmware_path),
            brand=brand,
            profile=profile,
        )
        self._runs[run_id] = state
        if self._queue is not None:
            await self._queue.put(state)
        return run_id

    def get(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def get_all(self) -> list[RunState]:
        return sorted(self._runs.values(), key=lambda r: r.queued_at, reverse=True)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q, _ = self.subscribe_with_history(run_id)
        return q

    def subscribe_with_history(self, run_id: str) -> tuple[asyncio.Queue, list[dict]]:
        """
        Register a subscriber and atomically snapshot the events emitted so far.

        Runs synchronously (no await) so no event can slip in between the
        history snapshot and the queue registration — a late subscriber to a
        still-running job replays the backlog, then picks up live events with
        no gap and no duplicates.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        backlog = list(self._history.get(run_id, ()))
        self._subscribers.setdefault(run_id, []).append(q)
        return q, backlog

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(run_id, [])
        if q in subs:
            subs.remove(q)

    def _emit(self, run_id: str, event: dict) -> None:
        """Broadcast an event to all subscribers. Must run on the event loop thread."""
        self._history.setdefault(run_id, deque(maxlen=_HISTORY_MAX)).append(event)
        for q in list(self._subscribers.get(run_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def _worker(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            state = await self._queue.get()  # type: ignore
            state.status = "running"
            state.started_at = datetime.now(timezone.utc).isoformat()
            self._emit(state.run_id, {"type": "status", "status": "running"})

            pub = QueuePublisher(state.run_id, self, loop)

            def _run(s=state, p=pub):
                from src.orchestrator import analyse_firmware

                fw = Path(s.firmware_path)
                orig_stdout = sys.stdout

                def emit_log(event: dict) -> None:
                    loop.call_soon_threadsafe(self._emit, s.run_id, event)

                sys.stdout = _StdoutCapture(emit_log)
                try:
                    return analyse_firmware(fw, s.brand, profile=s.profile, publisher=p)
                finally:
                    sys.stdout = orig_stdout

            try:
                result = await loop.run_in_executor(self._executor, _run)
                state.status = result.status
                state.report_path = str(result.report_path) if result.report_path else None
                if result.probe:
                    state.services = len(result.probe.services)
                state.cves = len(result.cve_matches)
                state.cred_hits = sum(1 for c in result.credentials if c.success)
                state.web_findings = len(result.web_findings)
            except Exception as exc:
                state.status = "failed"
                state.error = f"{type(exc).__name__}: {exc}"
            finally:
                state.completed_at = datetime.now(timezone.utc).isoformat()
                self._emit(state.run_id, {
                    "type": "status",
                    "status": state.status,
                    "state": state.to_dict(),
                })
                self._emit(state.run_id, {"type": "done"})
                self._queue.task_done()  # type: ignore
