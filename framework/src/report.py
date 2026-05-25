"""
Reporting module.
v1: writes a JSON report combining emulation and probe results.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

def write_report(firmware_path, emulation, probe, output_dir: Path) -> Path:
    """
    Write a structured JSON report describing the analysis run.
    Returns the path to the written report.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    name = Path(firmware_path).stem
    report_path = output_dir / f"{name}-{timestamp.replace(':', '-')}.json"

    report = {
        "firmware": {
            "path": str(firmware_path),
            "name": name,
        },
        "timestamp": timestamp,
        "emulation": {
            "image_id": emulation.image_id,
            "success": emulation.success,
            "architecture": emulation.architecture,
            "ip": emulation.ip,
            "web_service": emulation.web_service,
            "from_cache": emulation.from_cache,
        },
        "findings": probe.to_dict() if probe else None,
    }
    report_path.write_text(json.dumps(report, indent=2))
    return report_path