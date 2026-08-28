"""
Orchestrator.

analyse_firmware() is the canonical entry point for the framework.
Both run.py and the future web worker call this function; neither
contains analysis logic of its own.
"""

import socket
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from src import acquisition, firmae_runner, probe, cve_matcher, credential_tester, web_prober, service_auditor, report
from src.events import NullPublisher, make_publisher
from src.acquisition import AcquisitionResult
from src.firmae_runner import EmulationResult
from src.probe import ProbeResult
from src.cve_matcher import CVEMatch
from src.credential_tester import CredentialResult
from src.web_prober import WebFinding


@dataclass
class AnalysisResult:
    run_id: str
    firmware_name: str
    status: str          # "success" | "emulation_failed" | "timeout" | "error"
    report_path: Path | None
    emulation: EmulationResult | None
    probe: ProbeResult | None
    cve_matches: list[CVEMatch]
    credentials: list[CredentialResult]
    web_findings: list[WebFinding]
    error: str | None = None


def analyse_firmware(
    firmware_path: Path,
    brand: str,
    profile: str = "comprehensive",
    config=None,
    publisher=None,
) -> AnalysisResult:
    """
    Run the full pipeline against one firmware image.

    config:    module-level config (defaults from config.py if None)
    publisher: EventPublisher instance (NullPublisher if None)
    """
    import config as _cfg
    cfg = config or _cfg

    run_id = uuid.uuid4().hex[:8]
    pub = publisher or NullPublisher(run_id)

    # ── 1. Acquisition ───────────────────────────────────────────────────────
    acq = acquisition.acquire(firmware_path, publisher=pub)

    # ── 2. FirmAE check ──────────────────────────────────────────────────────
    emulation = firmae_runner.check(
        firmware_path, brand,
        firmae_dir=cfg.FIRMAE_DIR,
        scratch_dir=cfg.SCRATCH_DIR,
        db_config=cfg.DB_CONFIG,
        publisher=pub,
    )

    if not emulation.success:
        report_path = report.write_report(
            acq, emulation, None, [], [], [],
            output_dir=cfg.REPORTS_DIR, run_id=run_id,
        )
        return AnalysisResult(
            run_id=run_id,
            firmware_name=acq.name,
            status="emulation_failed",
            report_path=report_path,
            emulation=emulation,
            probe=None,
            cve_matches=[],
            credentials=[],
            web_findings=[],
        )

    # ── 3. Start run mode ────────────────────────────────────────────────────
    run_proc = firmae_runner.start_run(
        firmware_path, brand, firmae_dir=cfg.FIRMAE_DIR, image_id=emulation.image_id,
    )

    probe_result = None
    cve_matches: list[CVEMatch] = []
    credentials: list[CredentialResult] = []
    web_findings: list[WebFinding] = []

    try:
        max_wait = getattr(cfg, "EMULATION_WAIT_SECONDS", 240)
        pub.progress("orchestrator", f"waiting up to {max_wait}s for firmware to come up")
        if not _wait_for_host(emulation.ip, timeout=max_wait):
            pub.progress("orchestrator", "firmware unreachable after timeout — scanning anyway")
        else:
            pub.progress("orchestrator", "firmware is up, proceeding to probe")

        # ── 4. Service enumeration ───────────────────────────────────────────
        probe_result = probe.probe_services(emulation.ip, profile=profile, publisher=pub)

        # ── 5. CVE matching ──────────────────────────────────────────────────
        cve_matches = cve_matcher.match_cves(
            probe_result.services, publisher=pub,
            api_key=getattr(cfg, "NVD_API_KEY", ""),
            rate_limit_sleep=getattr(cfg, "NVD_RATE_LIMIT_SLEEP", 6.0),
        )

        # Fallback: if every service is tcpwrapped / has no version banner, OR
        # if nmap found no services at all, look up CVEs by device model from
        # the firmware filename and brand string.
        no_version_info = not probe_result.services or all(
            s.service.lower() == "tcpwrapped" or not s.version
            for s in probe_result.services
        )
        if no_version_info and not cve_matches:
            cve_matches = cve_matcher.match_cves_by_firmware(
                acq.name, brand, publisher=pub,
                api_key=getattr(cfg, "NVD_API_KEY", ""),
                rate_limit_sleep=getattr(cfg, "NVD_RATE_LIMIT_SLEEP", 6.0),
            )

        # ── 6. Credential testing ────────────────────────────────────────────
        credentials = credential_tester.test_credentials(
            emulation.ip, probe_result.services, publisher=pub,
        )

        # ── 7. Service security audit (Telnet, FTP, SNMP, etc.) ─────────────
        service_findings = service_auditor.audit_services(
            emulation.ip, probe_result.services, publisher=pub,
        )

        # ── 8. Web probing ───────────────────────────────────────────────────
        web_findings = service_findings + web_prober.probe_web(
            emulation.ip, probe_result.services, publisher=pub,
        )

    finally:
        pub.progress("orchestrator", "stopping emulation")
        firmae_runner.stop_run(run_proc, image_id=emulation.image_id)

    # ── 8. Report ─────────────────────────────────────────────────────────
    report_path = report.write_report(
        acq, emulation, probe_result,
        cve_matches, credentials, web_findings,
        output_dir=cfg.REPORTS_DIR, run_id=run_id,
    )

    pub.success("orchestrator", {"report": str(report_path)})
    return AnalysisResult(
        run_id=run_id,
        firmware_name=acq.name,
        status="success",
        report_path=report_path,
        emulation=emulation,
        probe=probe_result,
        cve_matches=cve_matches,
        credentials=credentials,
        web_findings=web_findings,
    )


def _wait_for_host(ip: str, timeout: int = 240, poll_interval: int = 10) -> bool:
    """
    Poll until any common TCP port on the emulated firmware accepts a connection,
    or until timeout. Replaces a fixed sleep: embedded firmware boot time varies.
    """
    probe_ports = [80, 443, 53, 8080, 8181, 22]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for port in probe_ports:
            try:
                with socket.create_connection((ip, port), timeout=2):
                    print(f"[*] Firmware up (port {port} responded)")
                    return True
            except (socket.timeout, ConnectionRefusedError, OSError):
                pass
        elapsed = int(time.monotonic() - (deadline - timeout))
        print(f"[*] Waiting for firmware... ({elapsed}s elapsed)")
        time.sleep(poll_interval)
    return False
