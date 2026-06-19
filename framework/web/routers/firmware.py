import re
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, Form

import config

router = APIRouter()


def _derive_brand(vendor: str, stem: str) -> str:
    raw = f"{vendor}_{stem}".lower()
    brand = re.sub(r"[^a-z0-9_]+", "_", raw)
    return re.sub(r"_+", "_", brand).strip("_")[:60]


def _has_report(f: Path) -> bool:
    # v2 reports include file extension; v1 used stem only — check both
    return (
        any(config.REPORTS_DIR.glob(f"{f.name}-*.json"))
        or any(config.REPORTS_DIR.glob(f"{f.stem}-*.json"))
    )


@router.get("")
def list_firmware():
    fw_dir = config.FIRMWARE_DIR
    if not fw_dir.exists():
        return {"vendors": []}
    vendors = []
    for vendor_dir in sorted(fw_dir.iterdir()):
        if not vendor_dir.is_dir():
            continue
        images = []
        for f in sorted(vendor_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in config.FIRMWARE_EXTENSIONS:
                images.append({
                    "name":       f.name,
                    "path":       str(f),
                    "size":       f.stat().st_size,
                    "brand":      _derive_brand(vendor_dir.name, f.stem),
                    "has_report": _has_report(f),
                })
        if images:
            vendors.append({"name": vendor_dir.name, "images": images})
    return {"vendors": vendors}


@router.post("/upload")
async def upload_firmware(vendor: str = Form(...), file: UploadFile = None):
    if file is None or not file.filename:
        raise HTTPException(400, "No file provided")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in config.FIRMWARE_EXTENSIONS:
        raise HTTPException(400, f"Unsupported extension: {suffix}")
    # Sanitize: strip any path separators from the filename
    safe_name = Path(file.filename).name
    target_dir = config.FIRMWARE_DIR / vendor
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / safe_name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return {
        "name":   safe_name,
        "vendor": vendor,
        "path":   str(dest),
        "brand":  _derive_brand(vendor, dest.stem),
    }
