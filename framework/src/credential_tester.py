"""
Default credential testing.

Tests common username/password pairs against HTTP and SSH services
exposed by emulated firmware. Only records success/failure — no
post-authentication actions are taken (R-3).

R-1: the orchestrator validates the IP before calling this module.

Success detection uses positive indicators only (not absence of failure
keywords), because embedded firmware login pages frequently return HTTP 200
for every request regardless of credential validity.

HTTP Basic auth: the decisive signal is that the server must DISTINGUISH a
wrong password from a right one. A sentinel (known-wrong) password is sent
first; a real credential is only a success if the server responds
differently to it AND accepts it (non-4xx). If the server returns the same
status for the sentinel and the real attempt, it is not validating
credentials at that endpoint, and no success is recorded. Cookie/body
heuristics are NOT used for Basic auth: both the sentinel and the real
request carry an Authorization header, so any cookie-on-auth behaviour fires
for both and cannot distinguish valid from invalid.

HTTP form login: compared against a same-path sentinel-wrong-password POST,
using a new session cookie, a redirect away from a login path, or a body
that both differs from the sentinel and carries a success keyword.
"""

import logging
from dataclasses import dataclass, asdict

import requests

from src.probe import ServiceFinding
from src.events import NullPublisher

# Embedded SSH servers (e.g. old Dropbear builds) routinely offer only
# legacy KEX/cipher algorithms that modern paramiko refuses to negotiate.
# paramiko's Transport runs as a background thread and logs that failure
# itself (self._log(ERROR, ...)) regardless of what _test_ssh's own
# try/except catches on the calling thread - with no logging configured
# elsewhere, Python's handler-of-last-resort prints it as a raw traceback.
# This is expected, frequent, and not a real error - silence it here.
logging.getLogger("paramiko").setLevel(logging.CRITICAL)

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
        # nmap reports "tcpwrapped" when a port accepts a connection then
        # closes without completing the service handshake. These are not
        # confirmed HTTP services; the corrected Basic-auth logic below will
        # reject them anyway, but they are skipped here to avoid wasting
        # requests on ports that do not speak HTTP.
        if svc.service.lower() == "tcpwrapped":
            continue

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

    for username, password in DEFAULT_CREDENTIALS:
        hit = _try_http_basic(base_url, svc, username, password)
        if hit:
            results.append(hit)
            continue
        hit = _try_http_post(base_url, svc, username, password)
        if hit:
            results.append(hit)

    return results


def _try_http_basic(
    base_url: str,
    svc: ServiceFinding,
    username: str,
    password: str,
) -> CredentialResult | None:
    """
    HTTP Basic auth success detection.

    The decisive signal is that the server must respond DIFFERENTLY to a
    wrong password than to a right one. A sentinel (known-wrong) password
    establishes the baseline. A real credential is a success only if:
      - the server responds with a different status code than for the
        sentinel (so it is actually validating credentials), AND
      - the real attempt is accepted (status < 400, i.e. not 401/403).

    If the sentinel and the real attempt get the same status, the endpoint
    is not authenticating (e.g. HTTP 200 for everything, or 401 for
    everything), and no success is recorded. Cookie and body heuristics are
    deliberately NOT used here: both requests carry an Authorization header,
    so any cookie-on-auth behaviour fires identically for valid and invalid
    attempts and cannot distinguish them.
    """
    try:
        # Baseline: same username with a known-wrong sentinel password.
        s_wrong = requests.Session()
        s_wrong.verify = False
        wrong = s_wrong.get(base_url, auth=(username, _SENTINEL_PASSWORD),
                            timeout=_REQUEST_TIMEOUT)

        # Real attempt.
        s = requests.Session()
        s.verify = False
        resp = s.get(base_url, auth=(username, password),
                     timeout=_REQUEST_TIMEOUT)

        # Server does not distinguish wrong from right -> not authenticating.
        if resp.status_code == wrong.status_code:
            return None

        # The valid attempt must itself be accepted (not 401/403/4xx).
        if resp.status_code >= 400:
            return None

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
) -> CredentialResult | None:
    for path in HTTP_LOGIN_PATHS:
        try:
            # Baseline: post a sentinel wrong password to this path first.
            # If the server returns the same response for any credential, it's
            # not actually authenticating (e.g. HNAP1 returning device info
            # for all POSTs).
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

            # Skip if status code identical to wrong-password attempt for
            # non-200/302 codes — same response means no authentication.
            if resp.status_code == wrong.status_code and resp.status_code not in (200, 302):
                continue

            # New session cookie relative to the sentinel attempt. Both
            # requests POST credentials, so a cookie appearing for the real
            # attempt but not the sentinel is a genuine positive signal.
            new_cookies = set(s.cookies.keys()) - set(s_wrong.cookies.keys())
            if new_cookies:
                return CredentialResult(
                    port=svc.port, service=svc.service,
                    username=username, password=password,
                    success=True, method="http_post",
                )

            # Redirect to a non-login page that differs from the sentinel's
            # redirect target.
            if resp.status_code in (301, 302):
                location = resp.headers.get("Location", "").lower()
                wrong_loc = wrong.headers.get("Location", "").lower()
                if location != wrong_loc and not any(p in location for p in _LOGIN_PATH_PATTERNS):
                    return CredentialResult(
                        port=svc.port, service=svc.service,
                        username=username, password=password,
                        success=True, method="http_post",
                    )

            # 200 body that both differs from the sentinel AND carries a
            # success indicator.
            if resp.status_code == 200:
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