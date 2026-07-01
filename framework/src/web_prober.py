"""
Light web vulnerability probing.

Checks HTTP and HTTPS services on emulated firmware for common
misconfigurations and exposed admin paths. Non-mutating: reads only,
never posts or modifies state (R-3, R-4).

R-1: the orchestrator validates the IP before calling this module.
"""

from dataclasses import dataclass, asdict

import requests
import urllib3

from src.probe import ServiceFinding
from src.events import NullPublisher

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ADMIN_PATHS: list[tuple[str, str]] = [
    # Common router admin / CGI paths
    ("/admin",              "exposed_admin"),
    ("/cgi-bin/",           "exposed_admin"),
    ("/HNAP1/",             "exposed_admin"),
    ("/setup.cgi",          "exposed_admin"),
    ("/goform/",            "exposed_admin"),
    ("/webproc",            "exposed_admin"),
    ("/cgi-bin/webproc",    "exposed_admin"),
    ("/apply.cgi",          "exposed_admin"),
    ("/login.cgi",          "exposed_admin"),
    ("/syscmd.htm",         "exposed_admin"),
    ("/debug/",             "exposed_admin"),
    # IP camera / ONVIF paths
    ("/stream",             "exposed_stream"),
    ("/video",              "exposed_stream"),
    ("/snapshot",           "exposed_stream"),
    ("/image",              "exposed_stream"),
    ("/axis-cgi/",          "exposed_admin"),
    ("/onvif/",             "exposed_admin"),
]

SECURITY_HEADERS: list[str] = [
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Content-Security-Policy",
    "X-XSS-Protection",
]

VENDOR_FINGERPRINTS: list[tuple[str, str]] = [
    ("D-LINK",    "dlink"),
    ("ASUS",      "asus"),
    ("TP-LINK",   "tplink"),
    ("NETGEAR",   "netgear"),
    ("LINKSYS",   "linksys"),
    ("BELKIN",    "belkin"),
    ("TENDA",     "tenda"),
    ("ZYXEL",     "zyxel"),
    ("TRENDNET",  "trendnet"),
]

HTTP_SERVICE_NAMES  = {"http", "http-alt", "http-proxy", "webserver"}
HTTPS_SERVICE_NAMES = {"ssl/http", "ssl/https", "https", "ssl/https?"}
_HTTP_PORTS  = {80, 8080, 8181, 8182}
_HTTPS_PORTS = {443, 8443}
_REQUEST_TIMEOUT = 10


@dataclass
class WebFinding:
    port: int
    path: str
    finding_type: str
    detail: str
    severity: str    # "info", "low", "medium", "high"

    def to_dict(self) -> dict:
        return asdict(self)


def probe_web(
    ip: str,
    services: list[ServiceFinding],
    publisher: NullPublisher | None = None,
) -> list[WebFinding]:
    pub = publisher or NullPublisher()
    pub.start("web_prober", f"target={ip}")

    http_ports = [
        svc.port for svc in services
        if svc.service.lower() in HTTP_SERVICE_NAMES or svc.port in _HTTP_PORTS
    ]
    https_ports = [
        svc.port for svc in services
        if svc.service.lower() in HTTPS_SERVICE_NAMES or svc.port in _HTTPS_PORTS
    ]
    # Avoid double-probing a port already covered as plain HTTP
    https_ports = [p for p in https_ports if p not in http_ports]

    if not http_ports and not https_ports:
        pub.success("web_prober", {"findings": 0})
        return []

    findings: list[WebFinding] = []
    session = requests.Session()
    session.verify = False

    for port in http_ports:
        base_url = f"http://{ip}:{port}"
        pub.progress("web_prober", f"probing http port {port}")
        findings.extend(_check_admin_paths(session, base_url, port))
        root_resp = _get_root(session, base_url)
        if root_resp:
            findings.extend(_check_security_headers(root_resp, port))
            findings.extend(_check_vendor_fingerprint(root_resp, port))

    for port in https_ports:
        base_url = f"https://{ip}:{port}"
        pub.progress("web_prober", f"probing https port {port}")
        findings.extend(_check_admin_paths(session, base_url, port))
        root_resp = _get_root(session, base_url)
        if root_resp:
            findings.extend(_check_security_headers(root_resp, port))
            findings.extend(_check_vendor_fingerprint(root_resp, port))

    pub.success("web_prober", {"findings": len(findings)})
    return findings


def _get_root(session: requests.Session, base_url: str):
    try:
        return session.get(base_url, timeout=_REQUEST_TIMEOUT)
    except requests.RequestException:
        return None


def _check_admin_paths(
    session: requests.Session, base_url: str, port: int
) -> list[WebFinding]:
    findings = []
    for path, finding_type in ADMIN_PATHS:
        try:
            resp = session.get(
                f"{base_url}{path}", timeout=_REQUEST_TIMEOUT, allow_redirects=False
            )
            if resp.status_code in (200, 301, 302, 403):
                findings.append(WebFinding(
                    port=port,
                    path=path,
                    finding_type=finding_type,
                    detail=f"HTTP {resp.status_code} at {path}",
                    severity="medium" if resp.status_code == 200 else "low",
                ))
        except requests.RequestException:
            continue
    return findings


def _check_security_headers(resp, port: int) -> list[WebFinding]:
    findings = []
    present = {k.lower() for k in resp.headers}
    for header in SECURITY_HEADERS:
        if header.lower() not in present:
            findings.append(WebFinding(
                port=port,
                path="/",
                finding_type="missing_header",
                detail=f"Missing security header: {header}",
                severity="low",
            ))
    return findings


def _check_vendor_fingerprint(resp, port: int) -> list[WebFinding]:
    findings = []
    body_upper = resp.text.upper()
    for vendor_string, vendor_id in VENDOR_FINGERPRINTS:
        if vendor_string in body_upper:
            findings.append(WebFinding(
                port=port,
                path="/",
                finding_type="default_page",
                detail=f"Vendor-default web interface detected: {vendor_id}",
                severity="info",
            ))
            break
    return findings
