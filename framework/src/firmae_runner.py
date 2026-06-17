"""
FirmAE wrapper.

Responsible for invoking FirmAE in check or run mode and reading its
scratch directory to determine outcomes.

R-1: any firmware whose inferred IP is not RFC1918 private or loopback
is reclassified as emulation_failed. The framework never probes a
non-private IP, regardless of FirmAE's tap routing behaviour.
"""

import ipaddress
import subprocess
from dataclasses import dataclass
from pathlib import Path

import psycopg2

from src.events import NullPublisher


@dataclass
class EmulationResult:
    image_id: int | None
    success: bool
    architecture: str | None
    ip: str | None
    web_service: bool
    raw_log: str
    from_cache: bool = False


def check(
    firmware_path: Path,
    brand: str,
    use_cache: bool = True,
    firmae_dir: Path | None = None,
    scratch_dir: Path | None = None,
    db_config: dict | None = None,
    publisher: NullPublisher | None = None,
) -> EmulationResult:
    """
    Run FirmAE in check mode. Returns outcome including inferred IP.
    If the inferred IP is non-private, success is forced to False (R-1).
    """
    from config import FIRMAE_DIR, SCRATCH_DIR, DB_CONFIG
    firmae_dir  = firmae_dir  or FIRMAE_DIR
    scratch_dir = scratch_dir or SCRATCH_DIR
    db_config   = db_config   or DB_CONFIG
    pub = publisher or NullPublisher()

    pub.start("emulation", firmware_path.name)

    if use_cache:
        cached_id = _find_cached_image(firmware_path, db_config)
        if cached_id is not None:
            cached = _load_cached_result(cached_id, scratch_dir)
            if cached is not None:
                cached = _apply_ip_check(cached)
                pub.success("emulation", {"from_cache": True, "image_id": cached_id})
                return cached

    pub.progress("emulation", "running FirmAE check mode")
    cmd = ["sudo", "./run.sh", "-c", brand, str(firmware_path)]
    proc = subprocess.run(
        cmd,
        cwd=firmae_dir,
        capture_output=True,
        text=True,
        timeout=900,
    )
    log = proc.stdout + proc.stderr
    image_id = _extract_image_id(log)

    if image_id is None:
        pub.failure("emulation", "could not extract image ID from FirmAE output")
        return EmulationResult(None, False, None, None, False, log)

    scratch = scratch_dir / str(image_id)
    result = EmulationResult(
        image_id=image_id,
        success=_read_text(scratch / "result").strip().lower() == "true",
        architecture=_read_text(scratch / "architecture").strip() or None,
        ip=_read_text(scratch / "ip").strip() or None,
        web_service=bool(_read_text(scratch / "web").strip()),
        raw_log=log,
    )
    result = _apply_ip_check(result)

    if result.success:
        pub.success("emulation", {"image_id": image_id, "ip": result.ip, "arch": result.architecture})
    else:
        pub.failure("emulation", f"emulation failed for image_id={image_id}")
    return result


def start_run(
    firmware_path: Path,
    brand: str,
    firmae_dir: Path | None = None,
) -> subprocess.Popen:
    """Start FirmAE in run mode (background). Caller must call stop_run()."""
    from config import FIRMAE_DIR
    firmae_dir = firmae_dir or FIRMAE_DIR
    cmd = ["sudo", "./run.sh", "-r", brand, str(firmware_path)]
    return subprocess.Popen(
        cmd,
        cwd=firmae_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_run(proc: subprocess.Popen) -> None:
    """Terminate a running FirmAE emulation cleanly."""
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    subprocess.run(["sudo", "pkill", "qemu-system"], check=False)


# ── private helpers ──────────────────────────────────────────────────────────

def _apply_ip_check(result: EmulationResult) -> EmulationResult:
    """Enforce R-1: non-private inferred IPs reclassify the run as failed."""
    if result.ip and not _is_private_ip(result.ip):
        print(
            f"[!] Non-private IP inferred ({result.ip}) — reclassifying as "
            f"emulation_failed (R-1). FirmAE tap routing would keep traffic "
            f"local, but the framework does not rely on that invariant."
        )
        result.success = False
        result.ip = None
    return result


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def _extract_image_id(log: str) -> int | None:
    for line in log.splitlines():
        if "[IID]" in line:
            try:
                return int(line.split("[IID]")[1].strip().split()[0])
            except (IndexError, ValueError):
                return None
    return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text()
    except (FileNotFoundError, PermissionError):
        return ""


def _find_cached_image(firmware_path: Path, db_config: dict) -> int | None:
    with psycopg2.connect(**db_config) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM image WHERE filename = %s",
                (firmware_path.name,),
            )
            row = cur.fetchone()
            return row[0] if row else None


def _load_cached_result(image_id: int, scratch_dir: Path) -> EmulationResult | None:
    scratch = scratch_dir / str(image_id)
    if not (scratch / "result").exists():
        return None
    return EmulationResult(
        image_id=image_id,
        success=_read_text(scratch / "result").strip().lower() == "true",
        architecture=_read_text(scratch / "architecture").strip() or None,
        ip=_read_text(scratch / "ip").strip() or None,
        web_service=bool(_read_text(scratch / "web").strip()),
        raw_log="(loaded from cache)",
        from_cache=True,
    )
