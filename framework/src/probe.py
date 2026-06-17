"""
Dynamic analysis probes against a running emulated firmware.
Service enumeration and banner grabbing via nmap.
"""

import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal

from src.events import NullPublisher

ScanProfileName = Literal["fast", "comprehensive", "stealth"]

SCAN_PROFILES: dict[ScanProfileName, dict] = {
    "fast": {
        "description": "Top 1000 TCP ports, aggressive timing",
        "args": ["-Pn", "-sT", "-sV", "--top-ports", "1000", "-T4", "--max-retries", "1"],
        "timeout": 180,
    },
    "comprehensive": {
        "description": "All 65535 TCP ports, aggressive timing",
        "args": ["-Pn", "-sT", "-sV", "-p-", "-T4", "--min-rate", "1000", "--max-retries", "1"],
        "timeout": 600,
    },
    "stealth": {
        "description": "Top 1000 TCP ports, conservative timing for fragile firmware",
        "args": ["-Pn", "-sT", "-sV", "--top-ports", "1000", "-T2", "--max-retries", "2"],
        "timeout": 600,
    },
}


@dataclass
class ServiceFinding:
    port: int
    protocol: str
    service: str
    version: str
    raw_banner: str


@dataclass
class ProbeResult:
    ip: str
    scan_profile: ScanProfileName
    services: list[ServiceFinding] = field(default_factory=list)
    raw_output: str = ""
    scan_duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ip": self.ip,
            "scan_profile": self.scan_profile,
            "scan_duration_seconds": self.scan_duration_seconds,
            "services": [asdict(s) for s in self.services],
            "raw_output": self.raw_output,
        }


def probe_services(
    ip: str,
    profile: ScanProfileName = "comprehensive",
    publisher: NullPublisher | None = None,
) -> ProbeResult:
    pub = publisher or NullPublisher()

    if profile not in SCAN_PROFILES:
        raise ValueError(f"Unknown profile: {profile}. Available: {list(SCAN_PROFILES)}")

    config = SCAN_PROFILES[profile]
    cmd = ["sudo", "nmap", *config["args"], ip]

    pub.start("probe", f"profile={profile} target={ip}")
    start = time.monotonic()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=config["timeout"],
    )
    duration = time.monotonic() - start
    services = _parse_nmap(proc.stdout)

    pub.success("probe", {"services_found": len(services), "duration_seconds": round(duration, 1)})
    return ProbeResult(
        ip=ip,
        scan_profile=profile,
        services=services,
        raw_output=proc.stdout,
        scan_duration_seconds=round(duration, 1),
    )


def _parse_nmap(output: str) -> list[ServiceFinding]:
    findings = []
    in_port_table = False
    for line in output.splitlines():
        if line.startswith("PORT"):
            in_port_table = True
            continue
        if in_port_table:
            if not line.strip() or line.startswith("MAC ") or line.startswith("Service "):
                in_port_table = False
                continue
            parts = line.split(maxsplit=3)
            if len(parts) < 3 or "/" not in parts[0]:
                continue
            port_proto = parts[0].split("/")
            if parts[1] != "open":
                continue
            service = parts[2] if len(parts) >= 3 else ""
            version = parts[3] if len(parts) >= 4 else ""
            try:
                port = int(port_proto[0])
            except ValueError:
                continue
            findings.append(ServiceFinding(
                port=port,
                protocol=port_proto[1] if len(port_proto) > 1 else "tcp",
                service=service,
                version=version,
                raw_banner=line.strip(),
            ))
    return findings
