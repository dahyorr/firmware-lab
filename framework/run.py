"""
Single-firmware analysis entry point.

Usage: python3 run.py <firmware_path> <brand> [profile]
Profiles: fast, comprehensive (default), stealth
"""

import sys
import subprocess
from pathlib import Path

import config
from src.events import make_publisher
from src.orchestrator import analyse_firmware


def main(firmware_path: Path, brand: str, profile: str) -> int:
    print(f"[*] run_id will be assigned by orchestrator")
    print(f"[*] Firmware : {firmware_path.name}")
    print(f"[*] Brand    : {brand}")
    print(f"[*] Profile  : {profile}")

    pub = make_publisher("pending", config.VALKEY_HOST, config.VALKEY_PORT)

    try:
        result = analyse_firmware(firmware_path, brand, profile=profile, publisher=pub)
    except subprocess.TimeoutExpired as e:
        # firmae_runner already killed this image's own qemu/run.sh processes
        # before raising - no cleanup needed here. A blanket pkill would kill
        # sibling images running concurrently on the same host.
        print(f"[-] Timed out: {e}")
        return 1
    except Exception as e:
        print(f"[-] Error: {type(e).__name__}: {e}")
        return 1

    print(f"\n[*] run_id : {result.run_id}")
    print(f"[*] Status : {result.status}")
    if result.report_path:
        print(f"[*] Report : {result.report_path}")
    if result.probe:
        print(f"[+] Services found: {len(result.probe.services)}")
        for s in result.probe.services:
            print(f"      :{s.port}/{s.protocol}  {s.service}  {s.version}".rstrip())
    if result.cve_matches:
        print(f"[!] CVE matches: {len(result.cve_matches)}")
        for c in result.cve_matches:
            score = f" (CVSS {c.cvss_score})" if c.cvss_score else ""
            print(f"      {c.cve_id}{score} — port {c.port} {c.service} {c.version}")
    if any(r.success for r in result.credentials):
        print(f"[!] Valid credentials found:")
        for r in result.credentials:
            if r.success:
                pw = r.password if r.password else "(empty)"
                print(f"      port {r.port} — {r.username}:{pw} via {r.method}")
    if result.web_findings:
        print(f"[i] Web findings: {len(result.web_findings)}")
        for w in result.web_findings:
            print(f"      [{w.severity}] {w.finding_type} {w.path} — {w.detail}")

    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("Usage: python3 run.py <firmware_path> <brand> [profile]")
        print("Profiles: fast, comprehensive (default), stealth")
        sys.exit(2)
    firmware = Path(sys.argv[1]).resolve()
    profile  = sys.argv[3] if len(sys.argv) == 4 else "comprehensive"
    sys.exit(main(firmware, sys.argv[2], profile))
