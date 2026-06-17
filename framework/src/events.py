"""
Valkey pub/sub event publisher.

Every module emits start/progress/success/failure events so the future
web layer can subscribe for live status updates without any framework
changes (R-16).

Topic pattern: fw:{run_id}:{module}
Message format: JSON { event, module, run_id, ts, data }
"""

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventPublisher:
    def __init__(self, run_id: str, host: str = "localhost", port: int = 6379):
        import valkey
        self.run_id = run_id
        self._client = valkey.Valkey(host=host, port=port, decode_responses=True)

    def _publish(self, module: str, event: str, data: dict) -> None:
        topic = f"fw:{self.run_id}:{module}"
        msg = json.dumps({
            "event":  event,
            "module": module,
            "run_id": self.run_id,
            "ts":     _now(),
            "data":   data,
        })
        self._client.publish(topic, msg)

    def start(self, module: str, detail: str = "") -> None:
        self._publish(module, "start", {"detail": detail})

    def progress(self, module: str, msg: str) -> None:
        self._publish(module, "progress", {"msg": msg})

    def success(self, module: str, data: dict | None = None) -> None:
        self._publish(module, "success", data or {})

    def failure(self, module: str, error: str) -> None:
        self._publish(module, "failure", {"error": error})


class NullPublisher:
    """No-op publisher used when Valkey is unavailable or not needed."""

    def __init__(self, run_id: str = ""):
        self.run_id = run_id

    def start(self, module: str, detail: str = "") -> None:
        pass

    def progress(self, module: str, msg: str) -> None:
        pass

    def success(self, module: str, data: dict | None = None) -> None:
        pass

    def failure(self, module: str, error: str) -> None:
        pass


def make_publisher(run_id: str, host: str, port: int) -> EventPublisher | NullPublisher:
    """Return a real publisher, falling back to NullPublisher if Valkey is unreachable."""
    try:
        pub = EventPublisher(run_id, host, port)
        pub._client.ping()
        return pub
    except Exception:
        print("[!] Valkey not reachable — events will be suppressed")
        return NullPublisher(run_id)
