import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

import config

router = APIRouter()


@router.get("")
def list_reports():
    reports = []
    for f in sorted(
        config.REPORTS_DIR.glob("*.json"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    ):
        try:
            data = json.loads(f.read_text())
            em = data.get("emulation", {})
            if em.get("success"):
                status = "success"
            elif em:
                status = "emulation_failed"
            else:
                status = data.get("status")
            reports.append({
                "filename":     f.name,
                "firmware":     data.get("firmware", {}).get("name", f.stem),
                "timestamp":    data.get("timestamp"),
                "status":       status,
                "run_id":       data.get("run_id"),
                "architecture": em.get("architecture"),
                "ip":           em.get("ip"),
                "from_cache":   em.get("from_cache"),
                "services":     len(data.get("probe", {}).get("services", [])),
                "cves":         len(data.get("cve_matches", [])),
                "web_findings": len(data.get("web_findings", [])),
            })
        except Exception:
            pass
    return {"reports": reports}


@router.get("/{filename}")
def get_report(filename: str):
    safe = Path(filename).name
    path = config.REPORTS_DIR / safe
    if not path.exists() or path.suffix != ".json":
        raise HTTPException(404, "Report not found")
    return json.loads(path.read_text())
