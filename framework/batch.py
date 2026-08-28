"""
Batch runner: analyse all firmware images in a directory.

Usage:
    python3 batch.py <firmware_dir> [profile] [--vendor <name>] [--limit N] [--force]

Examples:
    python3 batch.py ~/project/firmware/
    python3 batch.py ~/project/firmware/ fast --vendor dlink --limit 5
"""

import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import config
from src.events import make_publisher
from src.orchestrator import analyse_firmware

REPORTS_DIR  = config.REPORTS_DIR
SUMMARY_DIR  = REPORTS_DIR / "_summaries"


def derive_brand(firmware_path: Path, vendor: str) -> str:
    raw   = f"{vendor}_{firmware_path.stem}".lower()
    brand = re.sub(r"[^a-z0-9_]+", "_", raw)
    brand = re.sub(r"_+", "_", brand).strip("_")
    return brand[:60]


def already_analysed(firmware_path: Path) -> bool:
    return len(list(REPORTS_DIR.glob(f"{firmware_path.name}-*.json"))) > 0


def discover_firmware(
    root_dir: Path, vendor_filter: str | None = None
) -> list[tuple[str, Path]]:
    if not root_dir.exists():
        raise FileNotFoundError(f"Directory not found: {root_dir}")
    discovered = []
    for vendor_dir in sorted(root_dir.iterdir()):
        if not vendor_dir.is_dir():
            continue
        vendor = vendor_dir.name
        if vendor_filter and vendor != vendor_filter:
            continue
        for path in sorted(vendor_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in config.FIRMWARE_EXTENSIONS:
                discovered.append((vendor, path))
    return discovered


def run_one(vendor: str, firmware_path: Path, profile: str) -> dict:
    brand = derive_brand(firmware_path, vendor)
    start = time.monotonic()
    summary = {
        "vendor":           vendor,
        "firmware":         firmware_path.name,
        "brand":            brand,
        "profile":          profile,
        "started_at":       datetime.now(timezone.utc).isoformat(),
        "status":           "unknown",
        "duration_seconds": 0.0,
        "from_cache":       False,
        "architecture":     None,
        "ip":               None,
        "services_found":   0,
        "cve_matches":      0,
        "credential_hits":  0,
        "web_findings":     0,
        "run_id":           None,
        "report_path":      None,
        "error":            None,
    }

    pub = make_publisher("pending", config.VALKEY_HOST, config.VALKEY_PORT)

    try:
        print(f"\n{'='*70}")
        print(f"[*] [{vendor}] {firmware_path.name}  brand={brand}  profile={profile}")
        print(f"{'='*70}")

        result = analyse_firmware(firmware_path, brand, profile=profile, publisher=pub)

        summary["run_id"]      = result.run_id
        summary["status"]      = result.status
        summary["report_path"] = str(result.report_path) if result.report_path else None

        if result.emulation:
            summary["from_cache"]   = result.emulation.from_cache
            summary["architecture"] = result.emulation.architecture
            summary["ip"]           = result.emulation.ip
        if result.probe:
            summary["services_found"] = len(result.probe.services)
        summary["cve_matches"]     = len(result.cve_matches)
        summary["credential_hits"] = sum(1 for r in result.credentials if r.success)
        summary["web_findings"]    = len(result.web_findings)

        _print_summary(result)

    except subprocess.TimeoutExpired as e:
        # firmae_runner._run_check_with_early_exit already killed this
        # image's own qemu/run.sh processes before raising - no cleanup
        # needed here. A blanket `pkill qemu-system` would kill sibling
        # images running concurrently on the same host (see
        # notes/vpc-run-failure-diagnoses.md).
        print(f"[-] Timed out: {e}")
        summary["status"] = "timeout"
        summary["error"]  = str(e)
    except Exception as e:
        print(f"[-] Error: {type(e).__name__}: {e}")
        summary["status"] = "error"
        summary["error"]  = f"{type(e).__name__}: {e}"

    summary["duration_seconds"] = round(time.monotonic() - start, 1)
    return summary


def _print_summary(result) -> None:
    print(f"[*] run_id : {result.run_id}  status : {result.status}")
    if result.probe:
        for s in result.probe.services:
            print(f"      :{s.port}/{s.protocol}  {s.service}  {s.version}".rstrip())
    if result.cve_matches:
        print(f"[!] {len(result.cve_matches)} CVE match(es)")
    if any(r.success for r in result.credentials):
        hits = [r for r in result.credentials if r.success]
        print(f"[!] {len(hits)} valid credential(s)")
    if result.web_findings:
        print(f"[i] {len(result.web_findings)} web finding(s)")


def write_batch_summary(summaries: list[dict], profile: str) -> Path:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    timestamp    = datetime.now(timezone.utc).isoformat().replace(":", "-")
    summary_path = SUMMARY_DIR / f"batch-{timestamp}.json"

    by_vendor: dict = defaultdict(lambda: {
        "total": 0, "success": 0, "emulation_failed": 0,
        "timeout": 0, "error": 0,
    })
    for s in summaries:
        v = by_vendor[s["vendor"]]
        v["total"] += 1
        v[s["status"]] = v.get(s["status"], 0) + 1

    for vendor in by_vendor:
        fresh = [
            s for s in summaries
            if s["vendor"] == vendor and s["status"] == "success" and not s["from_cache"]
        ]
        by_vendor[vendor]["mean_duration_fresh"] = (
            round(sum(s["duration_seconds"] for s in fresh) / len(fresh), 1)
            if fresh else None
        )
        total = by_vendor[vendor]["total"]
        emulated = sum(
            1 for s in summaries
            if s["vendor"] == vendor and s["architecture"] is not None
        )
        by_vendor[vendor]["emulation_success_rate"] = (
            round(emulated / total, 3) if total else 0
        )

    fresh_all = [s for s in summaries if not s["from_cache"] and s["status"] == "success"]
    batch = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profile":   profile,
        "total_firmware": len(summaries),
        "outcomes": {
            k: sum(1 for s in summaries if s["status"] == k)
            for k in ("success", "emulation_failed", "timeout", "error")
        },
        "emulation_success_rate": (
            round(
                sum(1 for s in summaries if s["architecture"] is not None) / len(summaries),
                3,
            ) if summaries else 0
        ),
        "from_cache":          sum(1 for s in summaries if s["from_cache"]),
        "fresh_runs":          len(fresh_all),
        "mean_duration_fresh": (
            round(sum(s["duration_seconds"] for s in fresh_all) / len(fresh_all), 1)
            if fresh_all else None
        ),
        "by_vendor": dict(by_vendor),
        "results":   summaries,
    }
    summary_path.write_text(json.dumps(batch, indent=2))
    return summary_path


def main(
    root_dir: Path, profile: str,
    vendor: str | None, force: bool, limit: int | None,
) -> int:
    discovered = discover_firmware(root_dir, vendor_filter=vendor)
    if not discovered:
        print(f"No firmware images found in {root_dir}")
        return 1

    by_vendor: dict = defaultdict(list)
    for v, f in discovered:
        by_vendor[v].append(f)
    print(f"[*] Discovered {len(discovered)} images across {len(by_vendor)} vendors:")
    for v, files in sorted(by_vendor.items()):
        print(f"     - {v}: {len(files)} images")

    if not force:
        before     = len(discovered)
        discovered = [(v, f) for v, f in discovered if not already_analysed(f)]
        skipped    = before - len(discovered)
        if skipped:
            print(f"[i] Skipping {skipped} already analysed (--force to re-run)")
        if not discovered:
            print("[i] Nothing to do.")
            return 0

    if limit and limit < len(discovered):
        print(f"[i] Limit: processing first {limit} of {len(discovered)}")
        discovered = discovered[:limit]

    print(f"[*] Analysing {len(discovered)} images  profile={profile}")

    summaries  = []
    batch_start = time.monotonic()
    for i, (v, f) in enumerate(discovered, 1):
        print(f"\n[*] Image {i}/{len(discovered)}")
        summaries.append(run_one(v, f, profile))

    batch_duration = time.monotonic() - batch_start
    summary_path   = write_batch_summary(summaries, profile)

    print(f"\n{'='*70}")
    print(f"[*] Batch complete in {batch_duration:.0f}s ({batch_duration/60:.1f} min)")
    print(f"[*] Summary: {summary_path}")
    print(f"{'='*70}")
    print(f"    Total: {len(summaries)}")
    for status in ("success", "emulation_failed", "timeout", "error"):
        n = sum(1 for s in summaries if s["status"] == status)
        if n:
            print(f"    {status + ':':22} {n}")
    print()
    vendor_stats: dict = defaultdict(lambda: {"total": 0, "success": 0})
    for s in summaries:
        vendor_stats[s["vendor"]]["total"]   += 1
        if s["status"] == "success":
            vendor_stats[s["vendor"]]["success"] += 1
    for v, st in sorted(vendor_stats.items()):
        rate = st["success"] / st["total"] * 100 if st["total"] else 0
        print(f"    {v:28} {st['success']}/{st['total']} ({rate:.0f}%)")

    return 0


def _parse_args(argv: list[str]) -> tuple[Path, str, str | None, bool, int | None]:
    if len(argv) < 2:
        print(__doc__)
        sys.exit(2)
    root_dir = Path(argv[1]).resolve()
    profile  = "comprehensive"
    vendor   = None
    force    = False
    limit    = None
    i = 2
    while i < len(argv):
        arg = argv[i]
        if arg in ("fast", "comprehensive", "stealth"):
            profile = arg
        elif arg == "--force":
            force = True
        elif arg == "--vendor" and i + 1 < len(argv):
            vendor = argv[i + 1]; i += 1
        elif arg == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1]); i += 1
        else:
            print(f"Unknown argument: {arg}"); print(__doc__); sys.exit(2)
        i += 1
    return root_dir, profile, vendor, force, limit


if __name__ == "__main__":
    root_dir, profile, vendor, force, limit = _parse_args(sys.argv)
    sys.exit(main(root_dir, profile, vendor, force, limit))
