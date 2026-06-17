"""
Acquisition module.

Validates the firmware path exists, computes its SHA256 hash, and returns
a structured result. This is the first step in the pipeline and the only
place a firmware file's identity is established.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from config import FIRMWARE_EXTENSIONS
from src.events import NullPublisher


@dataclass
class AcquisitionResult:
    path: Path
    name: str
    sha256: str
    size_bytes: int


def acquire(
    firmware_path: Path,
    publisher: NullPublisher | None = None,
) -> AcquisitionResult:
    pub = publisher or NullPublisher()
    pub.start("acquisition", str(firmware_path))

    if not firmware_path.exists():
        pub.failure("acquisition", f"File not found: {firmware_path}")
        raise FileNotFoundError(f"Firmware not found: {firmware_path}")

    if firmware_path.suffix.lower() not in FIRMWARE_EXTENSIONS:
        pub.failure("acquisition", f"Unrecognised extension: {firmware_path.suffix}")
        raise ValueError(
            f"Unrecognised firmware extension '{firmware_path.suffix}'. "
            f"Expected one of: {FIRMWARE_EXTENSIONS}"
        )

    pub.progress("acquisition", "computing SHA256")
    sha256 = _sha256(firmware_path)
    size = firmware_path.stat().st_size

    pub.success("acquisition", {"sha256": sha256, "size_bytes": size})
    return AcquisitionResult(
        path=firmware_path,
        name=firmware_path.name,
        sha256=sha256,
        size_bytes=size,
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
