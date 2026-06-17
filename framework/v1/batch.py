"""
Batch runner: analyse all firmware images in a directory.

Usage:
    python3 batch.py <firmware_dir> [profile]

Examples:
    python3 batch.py ~/project/firmware/
    python3 batch.py ~/project/firmware/ fast

Skips firmware that already has a report unless --force is passed.
"""

import sys
import time
import re
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

from src import firmae_runner, probe, report

REPORTS_DIR = Path(__file__).parent / "reports"
SUMMARY_DIR = Path(__file__).parent / "reports" / "_summaries"

FIRMWARE_EXTENSIONS = {".zip", ".bin", ".img", ".trx", ".chk"}

def derive_brand(firmware_path: Path, vendor: str) -> str:
    """
    Generate a FirmAE brand label as <vendor>_<filename_stem>.
    Lowercased, alphanumerics + underscores, length-capped.
    """
    raw = f"{vendor}_{firmware_path.stem}".lower()
    brand = re.sub(r"[^a-z0-9_]+", "_", raw)
    brand = re.sub(r"_+", "_", brand).strip("_")
    return brand[:60]

def already_analysed(firmware_path: Path, vendor: str) -> bool:
    """Check if there's already a report for this firmware (vendor-aware)."""
    brand = derive_brand(firmware_path, vendor)
    matches = list(REPORTS_DIR.glob(f"{firmware_path.stem}-*.json"))
    return len(matches) > 0

def discover_firmware(root_dir: Path, vendor_filter: str | None = None) -> list[tuple[str, Path]]:
    """
    Walk subdirectories to find firmware images.
    Returns list of (vendor, firmware_path) tuples, sorted by vendor then name.
    """
    if not root_dir.exists():
        raise FileNotFoundError(f"Directory not found: {root_dir}")

    discovered = []
    for vendor_dir in sorted(root_dir.iterdir()):
        # print(vendor_dir)
        if not vendor_dir.is_dir():
            continue
        vendor = vendor_dir.name
        if vendor_filter and vendor != vendor_filter:
            continue
        for path in sorted(vendor_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in FIRMWARE_EXTENSIONS:
                discovered.append((vendor, path))
    return discovered

def analyse_one(vendor: str, firmware_path: Path, profile: str) -> dict:
    """
    Run the full pipeline against one firmware image.
    Returns a summary dict regardless of success or failure.
    """
    brand = derive_brand(firmware_path, vendor)
    start_time = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "vendor": vendor,
        "firmware": firmware_path.name,
        "brand": brand,
        "profile": profile,
        "started_at": started_at,
        "status": "unknown",
        "duration_seconds": 0.0,
        "from_cache": False,
        "architecture": None,
        "ip": None,
        "services_found": 0,
        "error": None,
    }

    try:
        print(f"\n{'='*70}")
        print(f"[*] [{vendor}] {firmware_path.name}")
        print(f"    brand: {brand}")
        print(f"    profile: {profile}")
        print(f"{'='*70}")

        emulation = firmae_runner.check(firmware_path, brand)
        summary["from_cache"] = emulation.from_cache
        summary["architecture"] = emulation.architecture
        summary["ip"] = emulation.ip

        if not emulation.success:
            print(f"[-] Emulation failed")
            summary["status"] = "emulation_failed"
            report.write_report(firmware_path, emulation, None, REPORTS_DIR)
            return summary

        if emulation.from_cache:
            print(f"[i] Cached emulation (IID {emulation.image_id})")
        print(f"[+] Emulated: {emulation.architecture} at {emulation.ip}")

        run_proc = firmae_runner.start_run(firmware_path, brand)
        try:
            print("[*] Waiting 90s for services to come up...")
            time.sleep(90)
            print(f"[*] Probing services (profile: {profile})...")
            probe_result = probe.probe_services(emulation.ip, profile=profile)
            summary["services_found"] = len(probe_result.services)
            print(f"[+] {len(probe_result.services)} services in "
                  f"{probe_result.scan_duration_seconds}s")
            for s in probe_result.services:
                print(f"      :{s.port}/{s.protocol} {s.service} {s.version}".rstrip())
        finally:
            print("[*] Stopping emulation...")
            firmae_runner.stop_run(run_proc)

        report.write_report(firmware_path, emulation, probe_result, REPORTS_DIR)
        summary["status"] = "success"

    except subprocess.TimeoutExpired as e:
        print(f"[-] Timed out: {e}")
        summary["status"] = "timeout"
        summary["error"] = str(e)
        subprocess.run(["sudo", "pkill", "qemu-system"], check=False)
    except Exception as e:
        print(f"[-] Error: {type(e).__name__}: {e}")
        summary["status"] = "error"
        summary["error"] = f"{type(e).__name__}: {e}"
        subprocess.run(["sudo", "pkill", "qemu-system"], check=False)

    summary["duration_seconds"] = round(time.monotonic() - start_time, 1)
    return summary


def write_batch_summary(summaries: list[dict], profile: str) -> Path:
    """Write a JSON summary of the whole batch run, with per-vendor breakdown."""
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-")
    summary_path = SUMMARY_DIR / f"batch-{timestamp}.json"

    # Per-vendor stats
    by_vendor = defaultdict(lambda: {
        "total": 0,
        "success": 0,
        "emulation_failed": 0,
        "timeout": 0,
        "error": 0,
        "mean_duration_fresh": None,
    })
    for s in summaries:
        v = by_vendor[s["vendor"]]
        v["total"] += 1
        v[s["status"]] = v.get(s["status"], 0) + 1

    # Mean duration for fresh successful runs per vendor
    for vendor in by_vendor:
        fresh_successes = [
            s for s in summaries
            if s["vendor"] == vendor and s["status"] == "success" and not s["from_cache"]
        ]
        if fresh_successes:
            by_vendor[vendor]["mean_duration_fresh"] = round(
                sum(s["duration_seconds"] for s in fresh_successes) / len(fresh_successes), 1
            )
        by_vendor[vendor]["emulation_success_rate"] = round(
            sum(1 for s in summaries
                if s["vendor"] == vendor and s["architecture"] is not None)
            / by_vendor[vendor]["total"], 3
        ) if by_vendor[vendor]["total"] else 0

    fresh = [s for s in summaries if not s["from_cache"] and s["status"] == "success"]

    batch = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "total_firmware": len(summaries),
        "outcomes": {
            "success": sum(1 for s in summaries if s["status"] == "success"),
            "emulation_failed": sum(1 for s in summaries if s["status"] == "emulation_failed"),
            "timeout": sum(1 for s in summaries if s["status"] == "timeout"),
            "error": sum(1 for s in summaries if s["status"] == "error"),
        },
        "emulation_success_rate": round(
            sum(1 for s in summaries if s["architecture"] is not None) / len(summaries), 3
        ) if summaries else 0,
        "from_cache": sum(1 for s in summaries if s["from_cache"]),
        "fresh_runs": len(fresh),
        "mean_duration_fresh": (
            round(sum(s["duration_seconds"] for s in fresh) / len(fresh), 1)
            if fresh else None
        ),
        "by_vendor": dict(by_vendor),
        "results": summaries,
    }
    summary_path.write_text(json.dumps(batch, indent=2))
    return summary_path


def main(root_dir: Path, profile: str, vendor: str | None, force: bool, limit: int | None) -> int:
    discovered = discover_firmware(root_dir, vendor_filter=vendor)
    if not discovered:
        print(f"No firmware images found in {root_dir}")
        if vendor:
            print(f"(with vendor filter: {vendor})")
        return 1

    # Group for nicer logging
    by_vendor = defaultdict(list)
    for v, f in discovered:
        by_vendor[v].append(f)
    print(f"[*] Discovered {len(discovered)} firmware images across {len(by_vendor)} vendors:")
    for v, files in sorted(by_vendor.items()):
        print(f"     - {v}: {len(files)} images")

    if not force:
        before = len(discovered)
        discovered = [
            (v, f) for v, f in discovered if not already_analysed(f, v)
        ]
        skipped = before - len(discovered)
        if skipped:
            print(f"[i] Skipping {skipped} firmware already analysed (use --force to re-run)")
        if not discovered:
            print("[i] Nothing to do.")
            return 0

    if limit and limit < len(discovered):
        print(f"[i] Limit applied: processing first {limit} of {len(discovered)} images")
        discovered = discovered[:limit]

    print(f"[*] Will analyse {len(discovered)} firmware images sequentially")
    print(f"[*] Profile: {profile}")

    summaries = []
    batch_start = time.monotonic()
    for i, (vendor, firmware_path) in enumerate(discovered, 1):
        print(f"\n[*] Image {i}/{len(discovered)}")
        summaries.append(analyse_one(vendor, firmware_path, profile))

    batch_duration = time.monotonic() - batch_start
    summary_path = write_batch_summary(summaries, profile)

    print(f"\n{'='*70}")
    print(f"[*] Batch complete in {batch_duration:.0f}s ({batch_duration/60:.1f} min)")
    print(f"[*] Summary: {summary_path}")
    print(f"{'='*70}")
    print(f"    Total:              {len(summaries)}")
    for status in ["success", "emulation_failed", "timeout", "error"]:
        count = sum(1 for s in summaries if s["status"] == status)
        if count:
            print(f"    {status + ':':20} {count}")
    print(f"\n    Per vendor:")
    vendor_stats = defaultdict(lambda: {"total": 0, "success": 0})
    for s in summaries:
        vendor_stats[s["vendor"]]["total"] += 1
        if s["status"] == "success":
            vendor_stats[s["vendor"]]["success"] += 1
    for v, st in sorted(vendor_stats.items()):
        rate = (st["success"] / st["total"] * 100) if st["total"] else 0
        print(f"     {v:25} {st['success']}/{st['total']} ({rate:.0f}%)")

    return 0


def parse_args(argv: list[str]) -> tuple[Path, str, str | None, bool, int | None]:
    if len(argv) < 2:
        print(__doc__)
        sys.exit(2)
    root_dir = Path(argv[1]).resolve()
    profile = "comprehensive"
    vendor = None
    force = False
    limit = None
    i = 2
    while i < len(argv):
        arg = argv[i]
        if arg in ("fast", "comprehensive", "stealth"):
            profile = arg
        elif arg == "--force":
            force = True
        elif arg == "--vendor" and i + 1 < len(argv):
            vendor = argv[i + 1]
            i += 1
        elif arg == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1])
            i += 1
        else:
            print(f"Unknown argument: {arg}")
            print(__doc__)
            sys.exit(2)
        i += 1
    return root_dir, profile, vendor, force, limit


if __name__ == "__main__":
    root_dir, profile, vendor, force, limit = parse_args(sys.argv)
    sys.exit(main(root_dir, profile, vendor, force, limit))