"""
CVE matching via NVD API v2.

For each discovered service with a version string, queries the National
Vulnerability Database and returns matching CVE records. Rate-limited
to stay within NVD's published thresholds (R-10: deterministic sleep,
no randomisation).

Version range filtering: after fetching results the CPE configuration
block is parsed to discard CVEs whose affected version ranges do not
include the detected version. CVEs with no machine-readable configuration
(common for pre-2005 entries) are kept as-is.
"""

import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import requests

from src.probe import ServiceFinding
from src.events import NullPublisher

NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "iot-firmware-assessment-framework/2"


@dataclass
class CVEMatch:
    port: int
    service: str
    version: str
    cve_id: str
    cvss_score: float | None
    severity: str | None
    description: str
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


def match_cves(
    services: list[ServiceFinding],
    publisher: NullPublisher | None = None,
    api_key: str = "",
    rate_limit_sleep: float = 6.0,
) -> list[CVEMatch]:
    pub = publisher or NullPublisher()
    pub.start("cve_matcher", f"{len(services)} services to check")

    queryable = [(s, _build_query(s)) for s in services]
    queryable = [(s, q) for s, q in queryable if q]
    if not queryable:
        pub.success("cve_matcher", {"matches": 0})
        return []

    if api_key:
        _SESSION.headers["apiKey"] = api_key

    matches: list[CVEMatch] = []
    for i, (svc, query) in enumerate(queryable):
        pub.progress("cve_matcher", f"querying NVD for: {query}")
        try:
            found = _query_nvd(svc, query)
            matches.extend(found)
        except Exception as e:
            pub.progress("cve_matcher", f"NVD query failed for '{query}': {e}")

        if i < len(queryable) - 1:
            time.sleep(rate_limit_sleep)

    pub.success("cve_matcher", {"matches": len(matches)})
    return matches


def _query_nvd(svc: ServiceFinding, query: str) -> list[CVEMatch]:
    params = {"keywordSearch": query, "resultsPerPage": 20}
    resp = _SESSION.get(NVD_API_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    detected_ver = _extract_version(svc.version)

    results = []
    for item in data.get("vulnerabilities", []):
        cve = item.get("cve", {})
        cve_id = cve.get("id", "")

        if detected_ver and not _is_version_applicable(cve, detected_ver, svc.service):
            continue

        desc = next(
            (d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"),
            "",
        )

        score, severity = _extract_cvss(cve)

        results.append(CVEMatch(
            port=svc.port,
            service=svc.service,
            version=svc.version,
            cve_id=cve_id,
            cvss_score=score,
            severity=severity,
            description=desc,
            url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
        ))
    return results


def _build_query(svc: ServiceFinding) -> str | None:
    """
    Build the NVD keyword query for a service finding.

    Searches by product name for maximum recall; version range filtering
    happens post-fetch via CPE data in _is_version_applicable().

    e.g. version="dnsmasq 2.15-OpenDNS-1" → query "dnsmasq"
         version="OpenSSH 8.9p1 Ubuntu"   → query "OpenSSH"
         version="WebServer"              → skip (no version, too noisy)
         version=""                       → skip
    """
    v = svc.version.strip()
    if not v:
        return None
    if " " in v:
        return v.split()[0]
    if re.search(r"\d", v):
        return svc.service
    return None


def _extract_version(version_str: str) -> str | None:
    """Extract the first dotted numeric version segment from an nmap version string."""
    m = re.search(r"(\d+\.\d+(?:\.\d+)*)", version_str)
    return m.group(1) if m else None


def _parse_version_tuple(v: str) -> tuple[int, ...] | None:
    """Parse a dotted version string into a comparable int tuple."""
    m = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?", v)
    if not m:
        return None
    return tuple(int(x) for x in m.groups() if x is not None)


def _version_in_range(
    detected: str,
    start_inc: str | None,
    start_exc: str | None,
    end_inc: str | None,
    end_exc: str | None,
) -> bool:
    """Return True if detected version satisfies all provided CPE range bounds."""
    v = _parse_version_tuple(detected)
    if v is None:
        return True  # can't parse — keep the CVE
    if start_inc:
        s = _parse_version_tuple(start_inc)
        if s and v < s:
            return False
    if start_exc:
        s = _parse_version_tuple(start_exc)
        if s and v <= s:
            return False
    if end_inc:
        e = _parse_version_tuple(end_inc)
        if e and v > e:
            return False
    if end_exc:
        e = _parse_version_tuple(end_exc)
        if e and v >= e:
            return False
    return True


def _is_version_applicable(cve: dict, detected_ver: str, service_name: str) -> bool:
    """
    Return True if the CVE's CPE configuration covers the detected version.

    Falls back to True when no machine-readable configuration is present —
    many older CVEs (pre-2005) lack version range data. A CVE that matches
    any relevant CPE node is kept; one where all relevant nodes exclude the
    detected version is discarded.
    """
    configurations = cve.get("configurations", [])
    if not configurations:
        return True  # no CPE data — can't filter, keep it

    svc_lower = service_name.lower()
    # Firmware-fallback path: keyword search was already model-specific, so we
    # skip the product-name filter and only apply version range checks.
    skip_product_filter = svc_lower == "firmware"

    for config in configurations:
        for node in config.get("nodes", []):
            for cpe_match in node.get("cpeMatch", []):
                if not cpe_match.get("vulnerable", True):
                    continue

                if not skip_product_filter:
                    # Only consider CPE entries plausibly related to this service
                    criteria = cpe_match.get("criteria", "").lower()
                    cpe_parts = criteria.split(":")
                    product = cpe_parts[4] if len(cpe_parts) > 4 else ""
                    if svc_lower not in product and product not in svc_lower:
                        continue

                start_inc = cpe_match.get("versionStartIncluding")
                start_exc = cpe_match.get("versionStartExcluding")
                end_inc   = cpe_match.get("versionEndIncluding")
                end_exc   = cpe_match.get("versionEndExcluding")

                # No version constraints on this CPE entry → matches all versions
                if not any([start_inc, start_exc, end_inc, end_exc]):
                    return True

                if _version_in_range(detected_ver, start_inc, start_exc, end_inc, end_exc):
                    return True

    # All relevant CPE nodes checked — none cover the detected version
    return False


def _extract_cvss(cve: dict) -> tuple[float | None, str | None]:
    metrics = cve.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key, [])
        if entries:
            data = entries[0].get("cvssData", {})
            return data.get("baseScore"), data.get("baseSeverity")
    return None, None


# ── firmware-level CVE fallback ───────────────────────────────────────────────

_VENDOR_NOISE = {
    "latest", "firmware", "patch", "us", "kr", "eu", "au", "global",
    "tplink", "tp", "link", "dlink", "netgear", "zyxel", "asus",
    "belkin", "linksys", "trendnet", "cisco", "buffalo",
}


def _model_from_brand(brand: str) -> str | None:
    """
    Derive an NVD-searchable model keyword from the user-supplied brand string.

    e.g. 'netgear_r7000'          → 'R7000'
         'tplink_wr940n_v4'       → 'WR940N'
         'dlink_dir615_reve'      → 'DIR615'
         'zyxel_latest_nbg6617_…' → 'NBG6617'
    """
    parts = brand.lower().split("_")
    for part in parts:
        if part in _VENDOR_NOISE:
            continue
        # Skip pure hardware-version tokens like 'v4', 'v6', 'reve'
        if re.fullmatch(r'v\d+', part) or re.fullmatch(r'rev[a-z]?', part):
            continue
        # Must contain at least one digit (model numbers do)
        if re.search(r'\d', part):
            return part.upper()
    return None


def _model_from_filename(filename: str) -> str | None:
    """
    Extract a NVD-searchable model keyword from the archive filename.

    Preserves hyphens that are part of model numbers (D-Link DIR-615)
    but strips trailing version suffixes (-V1.0.9.42).

    e.g. 'DIR-615_REVE_FIRMWARE_PATCH_5.14B01.zip' → 'DIR-615'
         'R7000-V1.0.9.42_10.2.44.zip'             → 'R7000'
         'TL-WR940N_US__V4_160617.zip'              → 'TL-WR940N'
    """
    stem = Path(filename).stem
    first = stem.split("_")[0]
    # Strip trailing explicit version suffix:
    #   -V1.0.9.42 (starts with V) or -1.0.9 (multi-dotted, ≥2 components)
    # but NOT -615 alone (that's part of the model number e.g. DIR-615).
    first = re.sub(r'-V\d[\d.]*$', '', first, flags=re.IGNORECASE)
    first = re.sub(r'-\d+\.\d[\d.]*$', '', first, flags=re.IGNORECASE)
    if re.search(r'\d', first):
        return first
    return None


def _version_from_filename(filename: str) -> str | None:
    """
    Extract the firmware version string from the archive filename.

    e.g. 'R7000-V1.0.9.42_10.2.44.zip'            → '1.0.9.42'
         'NBG6617_V1.00_ABCT.6_C0.zip'             → '1.00'
         'DIR-615_REVE_FIRMWARE_PATCH_5.14B01.zip' → '5.14'
    """
    stem = Path(filename).stem
    m = re.search(r'[-_]V?(\d+\.\d+(?:\.\d+(?:\.\d+)?)?)', stem, re.IGNORECASE)
    return m.group(1) if m else None


def match_cves_by_firmware(
    filename: str,
    brand: str,
    publisher: NullPublisher | None = None,
    api_key: str = "",
    rate_limit_sleep: float = 6.0,
) -> list[CVEMatch]:
    """
    Fallback CVE lookup using device model extracted from the firmware filename
    and brand string. Used when service detection returns only 'tcpwrapped'
    results (no version strings) so normal service-level matching cannot fire.

    Returns CVEMatch objects with port=0, service='firmware'.
    """
    pub = publisher or NullPublisher()

    # Prefer filename-derived model (preserves hyphens, e.g. DIR-615) over
    # brand-derived model (loses hyphens, e.g. DIR615 → no NVD results).
    model   = _model_from_filename(filename) or _model_from_brand(brand)
    version = _version_from_filename(filename)

    if not model:
        pub.progress("cve_matcher", f"firmware fallback: could not extract model from '{filename}' or brand '{brand}'")
        return []

    pub.progress("cve_matcher", f"firmware fallback CVE lookup: model={model} version={version}")

    if api_key:
        _SESSION.headers["apiKey"] = api_key

    # Build a synthetic ServiceFinding so we can reuse _query_nvd
    pseudo_svc = ServiceFinding(
        port=0,
        protocol="tcp",
        service="firmware",
        version=version or "",
        raw_banner="",
    )

    try:
        results = _query_nvd(pseudo_svc, model)
    except Exception as e:
        pub.progress("cve_matcher", f"firmware fallback NVD query failed: {e}")
        return []

    # If we have no version, keep all results; version filtering already ran in _query_nvd
    pub.progress("cve_matcher", f"firmware fallback: {len(results)} CVE(s) for {model}")
    return results
