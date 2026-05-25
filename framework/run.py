"""
Framework entry point.

Usage: python3 run.py <firmware_path> <brand>
"""

import sys
import time
from pathlib import Path

from src import firmae_runner, probe, report

REPORTS_DIR = Path(__file__).parent / "reports"

def main(firmware_path: Path, brand: str, profile: str = "comprehensive") -> int:
    print(f"[*] Analysing {firmware_path.name} (brand: {brand})")

    print("[*] Step 1: Check emulation...")
    emulation = firmae_runner.check(firmware_path, brand)

    if emulation.from_cache:
        print(f"[i] Using cached emulation result (IID {emulation.image_id})")
        
    if not emulation.success:
        print(f"[-] Emulation failed for {firmware_path.name}")
        report.write_report(firmware_path, emulation, None, REPORTS_DIR)
        return 1

    print(f"[+] Emulated successfully: {emulation.architecture} at {emulation.ip}")

    print("[*] Step 2: Starting run mode for probing...")
    run_proc = firmae_runner.start_run(firmware_path, brand)
    try:
        # Wait for the firmware to be probeable
        print("[*] Waiting 90s for services to come up...")
        time.sleep(90)

        print("[*] Step 3: Probing services...")
        probe_result = probe.probe_services(emulation.ip, profile=profile)
        print(f"[+] Found {len(probe_result.services)} open services in {probe_result.scan_duration_seconds}s")
        for s in probe_result.services:
            print(f"      :{s.port}/{s.protocol} {s.service} {s.version}".rstrip())

    finally:
        print("[*] Step 4: Stopping emulation...")
        firmae_runner.stop_run(run_proc)

    print("[*] Step 5: Writing report...")
    report_path = report.write_report(firmware_path, emulation, probe_result, REPORTS_DIR)
    print(f"[+] Report: {report_path}")

    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("Usage: python3 run.py <firmware_path> <brand> [profile]")
        print("Profiles: fast, comprehensive (default), stealth")
        sys.exit(2)
    firmware = Path(sys.argv[1]).resolve()
    profile = sys.argv[3] if len(sys.argv) == 4 else "comprehensive"
    sys.exit(main(firmware, sys.argv[2], profile))