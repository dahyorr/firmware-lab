"""
CVE matching via NVD API v2.

For each discovered service with a version string, queries the National
Vulnerability Database and returns matching CVE records. Rate-limited
to stay within NVD's published thresholds (R-10: deterministic sleep,
no randomisation).
"""

import time
from dataclasses import dataclass, asdict

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

    queryable = [s for s in services if s.version.strip()]
    if not queryable:
        pub.success("cve_matcher", {"matches": 0})
        return []

    if api_key:
        _SESSION.headers["apiKey"] = api_key

    matches: list[CVEMatch] = []
    for i, svc in enumerate(queryable):
        query = f"{svc.service} {svc.version}".strip()
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
    params = {"keywordSearch": query, "resultsPerPage": 5}
    resp = _SESSION.get(NVD_API_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("vulnerabilities", []):
        cve = item.get("cve", {})
        cve_id = cve.get("id", "")

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


def _extract_cvss(cve: dict) -> tuple[float | None, str | None]:
    metrics = cve.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key, [])
        if entries:
            data = entries[0].get("cvssData", {})
            return data.get("baseScore"), data.get("baseSeverity")
    return None, None
