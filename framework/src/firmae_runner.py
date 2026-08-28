"""
FirmAE wrapper.

Responsible for invoking FirmAE in check or run mode and reading its
scratch directory to determine outcomes.

R-1: any firmware whose inferred IP is not RFC1918 private or loopback
is reclassified as emulation_failed. The framework never probes a
non-private IP, regardless of FirmAE's tap routing behaviour.
"""

import ipaddress
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Queue, Empty

import psycopg2

from src.events import NullPublisher

_PANIC_MARKER = "Kernel panic"
_IID_RE = re.compile(r"\[IID\]\s*(\d+)")
_CHECK_TIMEOUT = 900
_POLL_INTERVAL = 3


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
    log, image_id, panicked = _run_check_with_early_exit(cmd, firmae_dir, scratch_dir)

    if image_id is None:
        if panicked:
            pub.failure("emulation", "kernel panic before an image ID could be extracted")
            return EmulationResult(None, False, None, None, False, log)
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
    image_id: int | None = None,
) -> subprocess.Popen:
    """
    Start FirmAE in run mode (background). Caller must call stop_run().
    Spawned in its own process group so stop_run can kill the full tree.

    image_id, when known (it always is by this point - check() already ran),
    scopes the pre-start tap cleanup to this image's own interfaces so a
    concurrently-running sibling image on the same host is left alone.
    """
    from config import FIRMAE_DIR
    firmae_dir = firmae_dir or FIRMAE_DIR
    _cleanup_tap_interfaces(image_id)
    cmd = ["sudo", "./run.sh", "-r", brand, str(firmware_path)]
    return subprocess.Popen(
        cmd,
        cwd=firmae_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )


def stop_run(proc: subprocess.Popen, image_id: int | None = None) -> None:
    """
    Terminate a running FirmAE emulation and its entire process tree, then
    clean up lingering tap interfaces. FirmAE does not clean these up on exit,
    and they cause an infinite VLAN-init loop on the next start_run call.

    NOTE: we send SIGTERM to the specific sudo PID rather than the process group
    because sudo's signal-forwarding behaviour re-delivers the signal to its caller
    when a group-kill is used, which would terminate the Python orchestrator.

    image_id scopes the QEMU/run.sh cleanup to this specific image. A blanket
    `pkill qemu-system` here would kill every other concurrently-running
    image on the same host under parallel execution - this used to do exactly
    that and was silently corrupting results whenever multiple images ran on
    one machine at once (see notes/vpc-run-failure-diagnoses.md). Falls back
    to the old blanket behaviour only if image_id is unknown (should not
    normally happen - orchestrator always has it from the check() result).
    """
    try:
        subprocess.run(["sudo", "kill", "-TERM", str(proc.pid)], check=False)
        proc.wait(timeout=15)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            subprocess.run(["sudo", "kill", "-KILL", str(proc.pid)], check=False)
        except ProcessLookupError:
            pass

    if image_id is not None:
        _kill_image_processes(image_id)
    else:
        subprocess.run(["sudo", "pkill", "-f", "run.sh -r"], check=False)
        subprocess.run(["sudo", "pkill", "qemu-system"], check=False)

    _cleanup_tap_interfaces(image_id)


def _cleanup_tap_interfaces(image_id: int | None = None) -> None:
    """
    Remove FirmAE tap interfaces so the next start_run can create them cleanly.

    Scoped to a single image_id when known, so cleanup never touches a
    sibling image's tap interfaces under concurrent parallel execution.
    Falls back to a machine-wide sweep only when image_id is unknown.
    """
    result = subprocess.run(["ip", "link", "show"], capture_output=True, text=True)
    if image_id is not None:
        vlan_pat = re.compile(rf'(tap{image_id}_0\.\d+)')
        base_pat = re.compile(rf'(tap{image_id}_0)\b')
    else:
        vlan_pat = re.compile(r'(tap\d+_0\.\d+)')
        base_pat = re.compile(r'(tap\d+_0)\b')
    # Delete VLAN sub-interfaces first (tap<n>_0.<x>), then the base tap<n>_0
    vlans = vlan_pat.findall(result.stdout)
    bases = base_pat.findall(result.stdout)
    for name in vlans:
        subprocess.run(["sudo", "ip", "link", "delete", name], capture_output=True, check=False)
    for name in bases:
        subprocess.run(["sudo", "ip", "link", "delete", name], capture_output=True, check=False)


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """
    Kill the top-level tracked process (the `sudo ./run.sh -c ...`
    invocation itself). This is a separate process entry from the QEMU
    child _kill_image_processes reaches, and can otherwise sit blocked
    waiting on its dead child forever. Never raises - proc.wait() is only
    used to reap, not as a correctness gate.
    """
    subprocess.run(["sudo", "kill", "-9", str(proc.pid)], check=False)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _kill_image_processes(image_id: int) -> None:
    """
    Kill only the QEMU/run.sh processes tied to this specific image_id's
    scratch directory. Safe to call under concurrent parallel execution -
    matches only this image's own scratch path, never a sibling's.
    """
    result = subprocess.run(
        ["pgrep", "-f", f"scratch/{image_id}/image.raw"], capture_output=True, text=True,
    )
    for pid in result.stdout.split():
        subprocess.run(["sudo", "kill", "-9", pid], check=False)
    subprocess.run(["sudo", "pkill", "-9", "-f", f"scratch/{image_id}/run.sh"], check=False)


def _run_check_with_early_exit(
    cmd: list[str], firmae_dir: Path, scratch_dir: Path,
) -> tuple[str, int | None, bool]:
    """
    Run FirmAE check mode, watching for the image ID and an early kernel
    panic in the live serial log so a dead-on-arrival guest doesn't sit out
    the full 900s timeout. Returns (log, image_id, panicked).

    Cleanup on both panic and the timeout ceiling is scoped to this image's
    own scratch id (via _kill_image_processes) - never a blanket
    `pkill qemu-system`, which would kill sibling images under concurrent
    parallel execution on the same host.
    """
    proc = subprocess.Popen(
        cmd, cwd=firmae_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    lines: list[str] = []
    q: Queue = Queue()

    def _reader():
        try:
            for line in proc.stdout:
                q.put(line)
        finally:
            q.put(None)

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    image_id: int | None = None
    panicked = False
    start = time.monotonic()

    while True:
        try:
            while True:
                line = q.get_nowait()
                if line is None:
                    break
                lines.append(line)
                if image_id is None:
                    m = _IID_RE.search(line)
                    if m:
                        image_id = int(m.group(1))
        except Empty:
            pass

        if proc.poll() is not None:
            break

        elapsed = time.monotonic() - start
        if elapsed > _CHECK_TIMEOUT:
            if image_id is not None:
                _kill_image_processes(image_id)
            _kill_process_tree(proc)
            raise subprocess.TimeoutExpired(cmd, _CHECK_TIMEOUT)

        if image_id is not None and not panicked:
            for log_name in ("qemu.initial.serial.log", "qemu.final.serial.log"):
                log_path = scratch_dir / str(image_id) / log_name
                try:
                    content = log_path.read_text(errors="ignore")
                except (FileNotFoundError, PermissionError):
                    continue
                if _PANIC_MARKER in content:
                    panicked = True
                    break

        if panicked:
            # _kill_image_processes only reaches the QEMU process and the
            # scratch/<id>/run.sh continuation - the top-level `proc` (the
            # `sudo ./run.sh -c ...` invocation itself) is a separate process
            # that can otherwise sit blocked waiting on its dead child,
            # leaving proc.wait() hanging indefinitely.
            _kill_image_processes(image_id)
            _kill_process_tree(proc)
            break

        time.sleep(_POLL_INTERVAL)

    return "".join(lines), image_id, panicked


# ── private helpers ──────────────────────────────────────────────────────────

def _apply_ip_check(result: EmulationResult) -> EmulationResult:
    """
    Enforce R-1 and loopback guard.

    Loopback (127.x.x.x): FirmAE bound to the host rather than a tap
    interface — scanning would target the host VM, not the firmware.
    Non-private: traffic would leave the lab network (R-1).
    Both cases are reclassified as emulation_failed so no probe runs.
    """
    if not result.ip:
        return result
    try:
        ip = ipaddress.ip_address(result.ip)
    except ValueError:
        result.success = False
        result.ip = None
        return result

    if ip.is_loopback:
        print(
            f"[!] Emulated IP is loopback ({result.ip}) — FirmAE bound to host "
            f"rather than a tap interface. Scanning would target the host VM, "
            f"not the firmware. Reclassifying as emulation_failed."
        )
        result.success = False
        result.ip = None
        return result

    if not ip.is_private:
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
    return ip.is_private


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
