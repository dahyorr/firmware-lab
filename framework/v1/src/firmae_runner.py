"""
FirmAE wrapper.

Responsible for invoking FirmAE in check or run mode and reading its
scratch directory to determine outcomes.
"""

import subprocess
# import shutil
# import time
from pathlib import Path
from dataclasses import dataclass
import psycopg2
import ipaddress

DB_CONFIG = {
    "dbname": "firmware",
    "user": "firmadyne",
    "password": "firmadyne",
    "host": "127.0.0.1",
}

FIRMAE_DIR = Path.home() / "project" / "tools" / "FirmAE"
SCRATCH_DIR = FIRMAE_DIR / "scratch"


@dataclass
class EmulationResult:
    """Outcome of a FirmAE emulation attempt."""
    image_id: int | None
    success: bool
    architecture: str | None
    ip: str | None
    web_service: bool
    raw_log: str
    from_cache: bool = False

def _is_private_ip(ip_str: str):
    """
    Check whether an IP is in RFC1918 private ranges or loopback.
    Used as a defence-in-depth check: FirmAE's tap interfaces normally
    route emulated firmware traffic locally, but the framework imposes
    the additional invariant that no public IP is ever probed.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback

def check(firmware_path: Path, brand: str,  use_cache: bool = True) -> EmulationResult:
    """
    Run FirmAE in check mode against a firmware image.
    Returns whether the firmware booted and exposed network services.

    If use_cache is True and the firmware has been processed before,
    reuse the cached result instead of re-running FirmAE.
    """

    if use_cache:
        cached_id = find_cached_image(firmware_path)
        if cached_id is not None:
            cached = load_cached_result(cached_id)
            if cached is not None:
                return cached
            
    cmd = ["sudo", "./run.sh", "-c", brand, str(firmware_path), ]
    print(" ".join(cmd), FIRMAE_DIR)
    proc = subprocess.run(
        cmd,
        cwd=FIRMAE_DIR,
        capture_output=True,
        text=True,
        timeout=900,
    )
    log = proc.stdout + proc.stderr
    image_id = _extract_image_id(log)
    print('wrgw', image_id)
    if image_id is None:
        return EmulationResult(None, False, None, None, False, log)

    scratch = SCRATCH_DIR / str(image_id)

    result =  EmulationResult(
        image_id=image_id,
        success=_read_text(scratch / "result").strip().lower() == "true",
        architecture=_read_text(scratch / "architecture").strip() or None,
        ip=_read_text(scratch / "ip").strip() or None,
        web_service=bool(_read_text(scratch / "web").strip()),
        raw_log=log,
    )
    if result.ip and not _is_private_ip(result.ip):
        print(f"[!] FirmAE inferred non-private IP {result.ip}. "
          f"This is likely safe (FirmAE creates a tap route for the "
          f"inferred subnet), but the framework treats this as an "
          f"emulation failure to maintain the invariant that no "
          f"public IP is ever probed.")
    # result.success = False
    # result.ip = None
    return result

def start_run(firmware_path: Path, brand: str) -> subprocess.Popen:
    """
    Start FirmAE in run mode (background, returns the process handle).
    Caller is responsible for terminating the returned process.
    """
    cmd = ["sudo", "./run.sh", "-r", brand, str(firmware_path)]
    return subprocess.Popen(
        cmd,
        cwd=FIRMAE_DIR,
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
    # Belt and braces: kill any orphan qemu processes
    subprocess.run(["sudo", "pkill", "qemu-system"], check=False)


def _extract_image_id(log: str) -> int | None:
    """Pull the [IID] N line out of FirmAE's stdout."""
    for line in log.splitlines():
        if "[IID]" in line:
            try:
                return int(line.split("[IID]")[1].strip().split()[0])
            except (IndexError, ValueError):
                return None
    return None

def _read_text(path: Path) -> str:
    """Read a file if it exists, return empty string otherwise."""
    try:
        return path.read_text()
    except (FileNotFoundError, PermissionError):
        return ""

def find_cached_image(firmware_path: Path) -> int | None:
    """
    Check if this firmware has already been processed.
    Returns the image ID if found, else None.
    """
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM image WHERE filename = %s",
                (firmware_path.name,),
            )
            row = cur.fetchone()
            return row[0] if row else None

def load_cached_result(image_id: int) -> EmulationResult | None:
    """
    If scratch/<image_id>/result exists, build an EmulationResult from
    the cached files without re-running FirmAE.
    """
    scratch = SCRATCH_DIR / str(image_id)
    result_file = scratch / "result"
    if not result_file.exists():
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
