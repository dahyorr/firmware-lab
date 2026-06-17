"""
Default credential testing.

Tests common username/password pairs against HTTP and SSH services
exposed by emulated firmware. Only records success/failure — no
post-authentication actions are taken (R-3).

R-1: the orchestrator validates the IP before calling this module.
"""

import base64
from dataclasses import dataclass, asdict

import requests

from src.probe import ServiceFinding
from src.events import NullPublisher

DEFAULT_CREDENTIALS: list[tuple[str, str]] = [
    ("admin",  "admin"),
    ("admin",  "password"),
    ("admin",  ""),
    ("admin",  "1234"),
    ("root",   "root"),
    ("root",   ""),
    ("user",   "user"),
    ("guest",  "guest"),
]

HTTP_LOGIN_PATHS: list[str] = [
    "/login.cgi",
    "/cgi-bin/login.cgi",
    "/HNAP1/",
    "/login",
    "/goform/login",
]

HTTP_SERVICE_NAMES = {"http", "http-alt", "http-proxy", "webserver"}

_FAILURE_KEYWORDS = frozenset(
    ["incorrect", "invalid", "failed", "error", "unauthorized", "denied"]
)

_REQUEST_TIMEOUT = 10


@dataclass
class CredentialResult:
    port: int
    service: str
    username: str
    password: str
    success: bool
    method: str

    def to_dict(self) -> dict:
        return asdict(self)


def test_credentials(
    ip: str,
    services: list[ServiceFinding],
    publisher: NullPublisher | None = None,
) -> list[CredentialResult]:
    pub = publisher or NullPublisher()
    pub.start("credential_tester", f"target={ip}")

    results: list[CredentialResult] = []

    for svc in services:
        if svc.service.lower() in HTTP_SERVICE_NAMES or svc.port in (80, 8080, 8181, 8182):
            pub.progress("credential_tester", f"testing HTTP on port {svc.port}")
            results.extend(_test_http(ip, svc))
        elif svc.service.lower() == "ssh" or svc.port == 22:
            pub.progress("credential_tester", f"testing SSH on port {svc.port}")
            results.extend(_test_ssh(ip, svc))

    successes = sum(1 for r in results if r.success)
    pub.success("credential_tester", {"tested": len(results), "successes": successes})
    return results


def _test_http(ip: str, svc: ServiceFinding) -> list[CredentialResult]:
    base_url = f"http://{ip}:{svc.port}"
    results = []
    session = requests.Session()
    session.verify = False

    for username, password in DEFAULT_CREDENTIALS:
        hit = _try_http_basic(session, base_url, svc, username, password)
        if hit:
            results.append(hit)
            continue
        hit = _try_http_post(session, base_url, svc, username, password)
        if hit:
            results.append(hit)

    return results


def _try_http_basic(
    session: requests.Session,
    base_url: str,
    svc: ServiceFinding,
    username: str,
    password: str,
) -> CredentialResult | None:
    try:
        resp = session.get(base_url, auth=(username, password), timeout=_REQUEST_TIMEOUT)
        success = resp.status_code == 200 and not _body_suggests_failure(resp.text)
        if success:
            return CredentialResult(
                port=svc.port, service=svc.service,
                username=username, password=password,
                success=True, method="http_basic",
            )
    except requests.RequestException:
        pass
    return None


def _try_http_post(
    session: requests.Session,
    base_url: str,
    svc: ServiceFinding,
    username: str,
    password: str,
) -> CredentialResult | None:
    for path in HTTP_LOGIN_PATHS:
        try:
            resp = session.post(
                f"{base_url}{path}",
                data={"username": username, "password": password},
                timeout=_REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            success = (
                resp.status_code in (200, 302)
                and not _body_suggests_failure(resp.text)
            )
            if success:
                return CredentialResult(
                    port=svc.port, service=svc.service,
                    username=username, password=password,
                    success=True, method="http_post",
                )
        except requests.RequestException:
            continue
    return None


def _test_ssh(ip: str, svc: ServiceFinding) -> list[CredentialResult]:
    try:
        import paramiko
    except ImportError:
        return []

    results = []
    for username, password in DEFAULT_CREDENTIALS:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                ip, port=svc.port,
                username=username, password=password,
                timeout=_REQUEST_TIMEOUT,
                banner_timeout=_REQUEST_TIMEOUT,
                auth_timeout=_REQUEST_TIMEOUT,
            )
            results.append(CredentialResult(
                port=svc.port, service=svc.service,
                username=username, password=password,
                success=True, method="ssh",
            ))
            client.close()
        except (paramiko.AuthenticationException, paramiko.SSHException, OSError):
            pass
    return results


def _body_suggests_failure(body: str) -> bool:
    lower = body.lower()
    return any(kw in lower for kw in _FAILURE_KEYWORDS)
