"""
Reporting module.

Writes a structured JSON report combining all pipeline outputs.
JSON is the canonical format; PDF generation is a future module
that consumes it.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.acquisition import AcquisitionResult
from src.firmae_runner import EmulationResult
from src.probe import ProbeResult
from src.cve_matcher import CVEMatch
from src.credential_tester import CredentialResult
from src.web_prober import WebFinding


def write_report(
    acq: AcquisitionResult,
    emulation: EmulationResult,
    probe: ProbeResult | None,
    cve_matches: list[CVEMatch],
    credentials: list[CredentialResult],
    web_findings: list[WebFinding],
    output_dir: Path,
    run_id: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    report_path = output_dir / f"{acq.name}-{timestamp.replace(':', '-')}.json"

    report = {
        "run_id":    run_id,
        "timestamp": timestamp,
        "firmware": {
            "path":       str(acq.path),
            "name":       acq.name,
            "sha256":     acq.sha256,
            "size_bytes": acq.size_bytes,
        },
        "emulation": {
            "image_id":    emulation.image_id,
            "success":     emulation.success,
            "architecture": emulation.architecture,
            "ip":          emulation.ip,
            "web_service": emulation.web_service,
            "from_cache":  emulation.from_cache,
        },
        "probe":       probe.to_dict() if probe else None,
        "cve_matches": [c.to_dict() for c in cve_matches],
        "credentials": [c.to_dict() for c in credentials],
        "web_findings": [w.to_dict() for w in web_findings],
    }

    report_path.write_text(json.dumps(report, indent=2))
    return report_path
