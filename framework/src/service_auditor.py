"""
Non-HTTP service security auditor.

Flags insecure or legacy services detected by nmap that the web prober
doesn't cover: Telnet, FTP, SNMP, TFTP, and BSD r-commands. The anonymous
FTP probe attempts a login without modifying server state (R-3: no exploitation).
"""

import ftplib

from src.probe import ServiceFinding
from src.web_prober import WebFinding
from src.events import NullPublisher

_INSECURE_PORTS: dict[int, tuple[str, str]] = {
    23:  ("Telnet service exposed — plaintext remote access",           "high"),
    21:  ("FTP service exposed — plaintext file transfer",              "medium"),
    161: ("SNMP service exposed — may leak device configuration",       "medium"),
    69:  ("TFTP service exposed — unauthenticated file access",         "high"),
    512: ("rexec service exposed — plaintext remote execution",         "high"),
    513: ("rlogin service exposed — plaintext remote login",            "high"),
    514: ("rsh service exposed — plaintext remote shell",               "high"),
}


def audit_services(
    ip: str,
    services: list[ServiceFinding],
    publisher: NullPublisher | None = None,
) -> list[WebFinding]:
    pub = publisher or NullPublisher()
    pub.start("service_auditor", f"target={ip}, {len(services)} services")

    findings: list[WebFinding] = []
    seen_ports: set[int] = set()

    for svc in services:
        if svc.port not in _INSECURE_PORTS or svc.port in seen_ports:
            continue
        seen_ports.add(svc.port)

        detail, severity = _INSECURE_PORTS[svc.port]
        if svc.version:
            detail = f"{detail} (version: {svc.version})"

        findings.append(WebFinding(
            port=svc.port,
            path="N/A",
            finding_type="insecure_service",
            detail=detail,
            severity=severity,
        ))

        if svc.port == 21:
            pub.progress("service_auditor", f"testing anonymous FTP on port {svc.port}")
            if _probe_ftp_anonymous(ip, svc.port):
                findings.append(WebFinding(
                    port=svc.port,
                    path="N/A",
                    finding_type="anonymous_ftp",
                    detail="Anonymous FTP login accepted — read access without credentials",
                    severity="high",
                ))

    pub.success("service_auditor", {"findings": len(findings)})
    return findings


def _probe_ftp_anonymous(ip: str, port: int) -> bool:
    """Attempt anonymous FTP login. Returns True if the server accepts it."""
    try:
        with ftplib.FTP(timeout=10) as ftp:
            ftp.connect(ip, port, timeout=10)
            ftp.login("anonymous", "probe@example.com")
            return True
    except Exception:
        return False
