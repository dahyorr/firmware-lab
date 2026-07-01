"""
Default credential testing.

Tests common username/password pairs against HTTP and SSH services
exposed by emulated firmware. Only records success/failure — no
post-authentication actions are taken (R-3).

R-1: the orchestrator validates the IP before calling this module.

Success detection uses positive indicators only (not absence of failure
keywords), because embedded firmware login pages frequently return HTTP 200
for every request regardless of credential validity:
  - New session cookie set in the POST response
  - 302/301 redirect to a URL that does not contain a login-path pattern
  - Response body contains admin-specific content ("logout", "sign out")
"""

from dataclasses import dataclass, asdict

import requests

from src.probe import ServiceFinding
from src.events import NullPublisher

DEFAULT_CREDENTIALS: list[tuple[str, str]] = [
    # Most common IoT/router defaults
    ("admin",         "admin"),
    ("admin",         "password"),
    ("admin",         ""),
    ("admin",         "1234"),
    ("admin",         "12345"),
    ("admin",         "123456"),
    ("admin",         "admin123"),
    ("admin",         "1111"),
    ("admin",         "0000"),
    ("admin",         "pass"),
    ("admin",         "changeme"),
    ("admin",         "default"),
    ("admin",         "888888"),
    # Root variants — common in embedded Linux
    ("root",          "root"),
    ("root",          ""),
    ("root",          "admin"),
    ("root",          "toor"),
    ("root",          "12345"),
    ("root",          "password"),
    ("root",          "pass"),
    # Known Mirai / botnet targets
    ("root",          "vizxv"),
    ("root",          "xc3511"),
    ("root",          "klv1234"),
    ("root",          "7ujMko0admin"),
    ("admin",         "7ujMko0admin"),
    # Vendor-specific defaults
    ("admin",         "1234567890"),  # TP-Link
    ("admin",         "smcadmin"),    # SMC
    ("admin",         "motorola"),    # Motorola
    ("admin",         "airlive"),     # AirLive
    ("admin",         "epicrouter"),  # EpicRouter
    # Generic accounts
    ("user",          "user"),
    ("user",          "password"),
    ("user",          "1234"),
    ("guest",         "guest"),
    ("guest",         ""),
    ("support",       "support"),
    ("supervisor",    "supervisor"),
    ("administrator", "administrator"),
    ("administrator", "password"),
    ("default",       "default"),
]

HTTP_LOGIN_PATHS: list[str] = [
    "/login.cgi",
    "/cgi-bin/login.cgi",
    "/HNAP1/",
    "/login",
    "/goform/login",
]

HTTP_SERVICE_NAMES = {"http", "http-alt", "http-proxy", "webserver"}

# Keywords that unambiguously indicate an authenticated session.
# Only "logout" is included because it requires you to be logged in.
# Generic device-info words (reboot, wireless, configuration) appear in
# unauthenticated HNAP/SOAP responses and produce false positives.
_SUCCESS_KEYWORDS = frozenset([
    "logout", "log out", "sign out", "signout",
])

# URL fragments that indicate the redirect target is a login page, not admin.
_LOGIN_PATH_PATTERNS = frozenset([
    "login", "signin", "auth", "logon",
])

# Used as a "known-wrong" sentinel to establish a baseline response for
# comparison. Real passwords won't match this.
_SENTINEL_PASSWORD = "INVALID_SENTINEL_xQZ9_2026"

_REQUEST_TIMEOUT = 10
_VERIFY_SSL = False


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

    # Capture pre-auth baseline: cookies and body before any login attempt.
    baseline_cookies: set[str] = set()
    try:
        s = requests.Session()
        s.verify = False
        baseline_resp = s.get(base_url, timeout=_REQUEST_TIMEOUT)
        baseline_cookies = set(s.cookies.keys())
    except requests.RequestException:
        pass

    for username, password in DEFAULT_CREDENTIALS:
        hit = _try_http_basic(base_url, svc, username, password, baseline_cookies)
        if hit:
            results.append(hit)
            continue
        hit = _try_http_post(base_url, svc, username, password, baseline_cookies)
        if hit:
            results.append(hit)

    return results


def _try_http_basic(
    base_url: str,
    svc: ServiceFinding,
    username: str,
    password: str,
    baseline_cookies: set[str],
) -> CredentialResult | None:
    try:
        s = requests.Session()
        s.verify = False
        resp = s.get(base_url, auth=(username, password), timeout=_REQUEST_TIMEOUT)
        if resp.status_code == 401:
            return None
        new_cookies = set(s.cookies.keys()) - baseline_cookies
        if new_cookies or _body_suggests_success(resp.text):
            return CredentialResult(
                port=svc.port, service=svc.service,
                username=username, password=password,
                success=True, method="http_basic",
            )
    except requests.RequestException:
        pass
    return None


def _try_http_post(
    base_url: str,
    svc: ServiceFinding,
    username: str,
    password: str,
    baseline_cookies: set[str],
) -> CredentialResult | None:
    for path in HTTP_LOGIN_PATHS:
        try:
            # Baseline: post a sentinel wrong password to this path first.
            # If the server returns the same response for any credential, it's
            # not actually authenticating (e.g. HNAP1 returning device info for all POSTs).
            s_wrong = requests.Session()
            s_wrong.verify = False
            wrong = s_wrong.post(
                f"{base_url}{path}",
                data={"username": username, "password": _SENTINEL_PASSWORD},
                timeout=_REQUEST_TIMEOUT,
                allow_redirects=False,
            )

            s = requests.Session()
            s.verify = False
            resp = s.post(
                f"{base_url}{path}",
                data={"username": username, "password": password},
                timeout=_REQUEST_TIMEOUT,
                allow_redirects=False,
            )

            # Skip if status code identical to wrong-password attempt — same response
            if resp.status_code == wrong.status_code and resp.status_code not in (200, 302):
                continue

            new_cookies = set(s.cookies.keys()) - baseline_cookies
            if new_cookies:
                return CredentialResult(
                    port=svc.port, service=svc.service,
                    username=username, password=password,
                    success=True, method="http_post",
                )
            if resp.status_code in (301, 302):
                location = resp.headers.get("Location", "").lower()
                wrong_loc = wrong.headers.get("Location", "").lower()
                if location != wrong_loc and not any(p in location for p in _LOGIN_PATH_PATTERNS):
                    return CredentialResult(
                        port=svc.port, service=svc.service,
                        username=username, password=password,
                        success=True, method="http_post",
                    )
            if resp.status_code == 200:
                # Body must differ from wrong-password AND contain a success indicator
                if resp.text != wrong.text and _body_suggests_success(resp.text):
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


def _body_suggests_success(body: str) -> bool:
    lower = body.lower()
    return any(kw in lower for kw in _SUCCESS_KEYWORDS)
