# Project Context: IoT Firmware Security Assessment Framework

*A self-contained brief for feeding to any LLM (ChatGPT, Claude, etc.) to get full working context on this project without access to the repo. Last updated: 2026-07-13.*

---

## 1. What this is

An MSc Cybersecurity dissertation project (Leeds Beckett University) by **Adebanjo Adedayo** (student ID 77591559), supervised by **"Mo"**. Methodology: **Design Science Research**.

**The artefact:** an automated pipeline that takes an IoT firmware image (router, IP camera, etc.) as input, emulates it in a sandboxed QEMU environment via **FirmAE**, and runs dynamic security analysis against the running emulated device — service enumeration, CVE matching, default-credential testing, dangerous-service auditing, and web-interface probing — producing a structured JSON report.

**The gap it fills:** FirmAE alone emulates firmware and stops there — raw scratch-directory outputs, no consolidation, no CVE correlation, no credential testing, no structured reporting. This project's contribution is *integration and consolidation*, not a new emulation technique. The threat model targeted is Mirai-style compromise: default credentials, known CVEs in exposed services, unnecessarily exposed management services.

**Repo:** `github.com/dahyorr/firmware-lab` (private).

---

## 2. Lab environment

- **Host:** Proxmox VE, AMD Ryzen 5 PRO 5650GE, 40GB RAM.
- **VM `firmdh`:** Ubuntu 22.04.4 LTS (24.04 was tried first and rejected — breaks FirmAE's install.sh via a PEP 668 cascade). 6 vCPU (`host` CPU type, AMD-V passthrough), 12GB RAM, 64GB VirtIO SCSI disk.
- **Networking:** dual NIC — `enp6s18` (management, 10.10.1.101) and `enp6s19` (lab, 10.10.80.101). Home topology: Windows workstation on 192.168.0.0/24 → opnsense bridge (192.168.0.3) → lab network 10.10.0.0/24 → VM.
- **Known network gotcha:** FirmAE hardcodes 192.168.0.0/24 for emulated firmware. When FirmAE brings up its `tap<iid>_0` interface, the kernel installs a more-specific route for 192.168.0.0/24 that out-competes the path back to the SSH client, killing the SSH session mid-run. **Fix:** a persistent `/32` route pinning the SSH client through the correct interface (`ip route add 192.168.0.11/32 via 10.10.1.1 dev enp6s18`, made permanent via a systemd oneshot unit). Took three wrong hypotheses (subnet collision, single-NIC limitation, host-route conflict) before landing on the real cause — worth citing in the dissertation as evidence of real integration work beyond packaging.
- **Snapshots:** base-installed → firmae-installed → firmae-working → first-emulation-success → dual-nic.

---

## 3. Architecture (v2 — current)

```
firmware file
    │
    ▼
[1] acquisition     → SHA256, size, path validated
    │
    ▼
[2] firmae_runner   → QEMU boot via FirmAE, private IP assigned
    │  (fails → write partial report, stop — R-1 enforced here)
    ▼
[3] probe           → nmap: open ports + version banners
    │
    ├──▶ [4] cve_matcher       → NVD API v2 queries per service + firmware-model fallback
    ├──▶ [5] credential_tester → HTTP Basic/POST + SSH against 42 default credential pairs
    ├──▶ [6] service_auditor   → Telnet/FTP/SNMP/TFTP/r-command exposure flags + anon FTP probe
    └──▶ [7] web_prober        → admin paths, missing security headers, vendor fingerprint
                │
                ▼
           [8] report          → JSON written to framework/reports/
```

All stages publish `start`/`progress`/`success`/`failure` events to Valkey pub/sub (topic `fw:{run_id}:{module}`), which the web UI streams live.

### Source map

| File | Role |
|---|---|
| `framework/config.py` | All configurable paths/DB/Valkey/NVD config — no hardcoded paths in modules |
| `framework/run.py` | Thin CLI, single firmware |
| `framework/batch.py` | Thin CLI, directory of firmware; skips already-analysed, retries errors/timeouts |
| `framework/src/orchestrator.py` | `analyse_firmware()` — the one canonical pipeline entry point |
| `framework/src/acquisition.py` | Stage 1 |
| `framework/src/firmae_runner.py` | Stage 2 — FirmAE wrapper (check mode, run mode, stop, cache detection) |
| `framework/src/probe.py` | Stage 3 — nmap, 3 profiles (`fast`/`comprehensive`/`stealth`) |
| `framework/src/cve_matcher.py` | Stage 4 — NVD API v2, version-range CPE filtering, rate-limited |
| `framework/src/credential_tester.py` | Stage 5 — 42 credential pairs, HTTP Basic/POST + SSH |
| `framework/src/service_auditor.py` | Stage 6 — dangerous-service exposure flags |
| `framework/src/web_prober.py` | Stage 7 — admin paths, headers, vendor fingerprint |
| `framework/src/report.py` | Stage 8 — JSON report writer |
| `framework/src/events.py` | `EventPublisher`/`NullPublisher` for Valkey pub/sub |
| `framework/web/` | FastAPI backend (routers: firmware, runs, reports) + `run_manager.py` |
| `framework/web/frontend/` | React + TS + Vite + Tailwind UI; live run streaming; PDF export (`exportPdf.ts`) |
| `framework/v1/` | Archived first version (superseded, kept for history) |

### Stage detail (for anyone extending the pipeline)

- **Emulation (stage 2):** two-phase FirmAE invocation. Check mode (`-c`) queries FirmAE's PostgreSQL `image` table by filename first — cache hit skips the 5–15 min extraction. IP is validated via Python's `ipaddress` module; loopback or non-private → reclassified `emulation_failed`, nothing downstream runs (**R-1**, independent of FirmAE's own tap routing). Run mode (`-r`) starts FirmAE as a background process in its own process group; orchestrator polls ports 80/22/53/8080/8181 every 10s up to 240s. Stop sends `SIGTERM` to the specific sudo PID (not the process group — an earlier bug here killed the orchestrator itself, see §5), then `pkill` for surviving QEMU, then tap cleanup.
- **CVE matching (stage 4):** per-service keyword query against NVD (e.g. `dnsmasq 2.15` → `"dnsmasq"`), 20 results/query, 6s sleep between requests (rate limit without API key). Version-range filtering parses CPE `versionStartIncluding/Excluding`/`versionEndIncluding/Excluding` as int tuples. Firmware-level fallback extracts a model string from the filename (e.g. `DIR-615_REVE...` → `"DIR-615"`) when no service has a version banner.
- **Credential testing (stage 5):** 42 pairs (expanded from 8) — IoT defaults, Mirai botnet targets (vizxv, xc3511, klv1234, 7ujMko0admin), vendor-specific defaults, generic accounts. HTTP Basic (new session/success keyword = hit), HTTP POST (5 hardcoded paths, sentinel baseline then diff), SSH (paramiko). Telnet/FTP/SNMP left to service auditor per **R-3** (no exploitation).
- **Service auditor (stage 6):** flags Telnet(23)/FTP(21)/SNMP(161)/TFTP(69)/rexec-rlogin-rsh(512-514) as exposed; attempts anonymous (read-only) FTP login only.
- **Web probing (stage 7):** 18 admin paths (generic + IP-camera-specific like `/stream`, `/onvif/`), 4 security headers checked, vendor fingerprint via body string match.

---

## 4. Hard rules (from SPEC.md — the project's single source of truth for what to build/not build)

**Safety**
- **R-1:** Every inferred IP must be validated RFC1918-private or loopback before any probing. Non-private → `emulation_failed`. (Observed once: a D-Link IP camera image inferred a real Swedish mobile IP, 2.65.87.199 — safe only because of FirmAE's own tap routing; R-1 is the framework's independent guarantee, not reliance on that.)
- **R-2:** No action of any kind against an unvalidated IP.
- **R-3:** No exploitation — CVE matches and credential hits are reported, never acted on further.
- **R-4:** No aggressive scanning (`nmap -A`/vuln scripts banned; comprehensive profile caps at `-T4 --min-rate 1000`).
- **R-5:** Only emulated firmware is ever probed, never real devices.

**Scope**
- **R-6:** Never modify FirmAE itself — quirks handled in the wrapper.
- **R-7:** No firmware-specific hardcoding (ports/IPs/paths/creds) — variation is data, not code.
- **R-8:** No decompilation/disassembly/fuzzing/symbolic execution/manual exploit dev.
- **R-9:** No deployment infrastructure in v1 (Next.js/S3/worker queue are documented as post-dissertation, ~1 week of scope, not built yet — though the web UI in §3 was in fact built ahead of that plan).

**Reproducibility**
- **R-10:** Deterministic — no LLM calls at runtime, no randomised behaviour.
- **R-11:** Every firmware produces exactly one report (success/emulation_failed/timeout/error — never a silent skip).
- **R-12:** `from_cache` flag preserved end-to-end; headline timing stats use fresh runs only.
- **R-13:** No more than one retry per image per batch run.

**Engineering discipline**
- **R-14:** Modules take explicit function arguments, no `sys.argv`/implicit context.
- **R-15:** All paths configurable, none hardcoded inside modules.
- **R-16:** Every module emits Valkey lifecycle events.
- **R-17:** No global mutable state.
- **R-18:** FirmAE invocations are strictly sequential, never parallel (unsafe under concurrency for its DB/networking state).
- **R-19:** No firmware binaries in git.

**Ethics**
- **R-20:** Any inferred-public-IP incident (even one correctly blocked by R-1) gets logged and disclosed to the supervisor.
- **R-21:** Coordinated disclosure (90-day vendor notice) for any undisclosed vulnerability found.
- **R-22:** Only firmware from manufacturer public downloads or academic datasets is in scope — ethics approval doesn't cover anything else.

---

## 5. Development history

1. **2026-05-14** — Lab VM built (Ubuntu 22.04, FirmAE prerequisites), Proxmox snapshotted.
2. **2026-05-15** — First successful emulation: D-Link DIR-868L revB 2.05b02. Manual nmap against it found dnsmasq 2.45 (2008-vintage, multiple CVEs) — first concrete proof of the framework's value proposition. Same day: diagnosed and fixed the FirmAE/SSH network conflict (§2).
3. **v1 build** — end-to-end single-firmware pipeline: cache detection (query FirmAE's Postgres `image` table + verify `scratch/<iid>/result`, chosen over cache-clearing since re-extraction costs 5–15 min for no benefit), JSON reporting, batch runner with vendor-aware brand naming.
4. **2026-06-07** — SPEC.md written, locking in v2 design decisions: Valkey pub/sub from day one (not deferred to v2), fully configurable paths, JSON as canonical format with PDF as a downstream consumer, thin orchestrator pattern (`run.py`/`batch.py` are argument-parsing shells around `analyse_firmware()`).
5. **v2 rebuild** — archived v1 to `framework/v1/`, rebuilt per SPEC: R-1 actually enforced (v1 had it commented out), hardcoded paths removed, added CVE matcher / credential tester / web prober modules that v1 lacked, removed duplicate orchestration logic that existed separately in `run.py` and `batch.py`.
6. **2026-06-17 — Batch run 1** (5 firmware, 3 vendors, cached): 5/5 (100%) emulation success for private-IP images; 1 rejected by R-1 (public IP). Found dnsmasq 2.15-OpenDNS-1 (10 CVEs) on Netgear AC1450, Dropbear SSH 2011.54 (30 CVEs) on TP-Link Archer C7. Also fixed a `stop_run()` bug: `sudo kill -TERM -{pgid}` was propagating SIGTERM back to the Python orchestrator itself via sudo's signal forwarding, killing the batch mid-run — fixed by targeting the specific PID instead of the process group.
7. **2026-06-17 — Batch run 2** (5 firmware, fresh extraction): 3/5 (60%) success. DIR-645/DIR-655 failed — FirmAE extracts the kernel but not the rootfs for that product line (proprietary SquashFS variant), a documented FirmAE limitation, not a framework bug. Notable **CVE false-negative**: AC1450 v1.0.0.36 carrying the same dnsmasq 2.15-OpenDNS-1 base version as v1.0.0.34 (which got 10 CVE hits) returned 0 CVEs — the "OpenDNS-1" vendor suffix broke NVD's keyword match. Documented as a limitation; version-range CPE filtering added later (see below) mitigates related classes of false negatives/positives.
8. **Web UI added** — FastAPI backend + React/TS/Vite/Tailwind frontend with live run streaming over Valkey, ahead of the SPEC's original "post-dissertation" timeline for this feature.
9. **Service auditor, PDF export, CVE version-range filtering** added — dangerous-service exposure flags, browser-side PDF report export, and CPE version-range comparison to reduce both false positives (matching unrelated CVE ranges) and false negatives (vendor-suffixed version strings).
10. **Credential list expanded from 8 to 42 pairs** (most recent commit) — broadened default-credential coverage per the known gap in §6 below.
11. **2026-07-02/03 — large corpus batch runs.** A 1116-image full-corpus `comprehensive` batch (`batch_20260702_105747.log`) hard-hung the VM at image 117/748 remaining — see §7 for the recurring VM-freeze issue. A follow-up comprehensive run (`batch_20260703_091046.log`) got to **image 206/686** before Postgres itself crashed mid-run (2026-07-03 14:33 UTC) and stayed down for **10 days** because systemd's `pg_ctlcluster`-wrapped auto-restart kept failing with a misleading `Can't open PID file ... Operation not permitted` (the real crash-recovery process never got a chance to run through that path). Fixed 2026-07-09 by manually running `sudo pg_ctlcluster 14 main start`, which performed WAL crash recovery cleanly (no data loss) and brought the DB back up correctly under systemd.
12. **2026-07-13 — batch resumed.** `batch.py ~/project/firmware/ comprehensive` restarted; it auto-skips the ~430+ already-analysed images (report-file glob check) and retries anything that errored/timed out, so no manual bookkeeping of "where it stopped" was needed. **628 JSON reports exist in `framework/reports/` as of this run.**

---

## 6. Known limitations (for the dissertation's limitations section)

- **Credential testing — hardcoded HTTP POST paths.** Only 5 login paths are POSTed to (`/login.cgi`, `/cgi-bin/login.cgi`, `/HNAP1/`, `/login`, `/goform/login`). Firmware with non-standard paths (`/cgi-bin/webproc`, `/apply.cgi`, `/Forms/login`, etc.) is only covered by HTTP Basic, if that. The web prober discovers admin paths independently but this is **not fed back** into credential testing — a real pipeline gap. Results should be phrased as "tested against common login paths," not "fully tested."
- **Credential testing — non-HTTP services excluded by design.** Telnet, FTP (beyond anonymous probe), SNMP, r-commands are flagged as *exposed* by the service auditor but never credential-tested (R-3: no exploitation). This means default Telnet creds — the primary Mirai vector — are never confirmed, only flagged as present.
- **Emulation coverage.** Of 217 tested images at one measurement point, 127 failed: 7 unsupported formats (unrecognised archive/binary layout), 75 with architecture identified but no IP assigned (kernel/network init failure at the QEMU level — mainly ASUS RT-N/AC and D-Link cameras), 49 with partial extraction and no architecture detected (older D-Link DIR-600/615/825 `.bin`/`.trx`). These are FirmAE-level limits; results should be scoped to "emulable firmware," not the full corpus.
- **CVE keyword matching false negatives.** Vendor-suffixed version strings (e.g. `2.15-OpenDNS-1`) can silently break NVD keyword matching even when the base version is known-vulnerable. Version-range CPE filtering (added later) narrows related error classes but does not eliminate this specific failure mode.

---

## 7. Operational incidents worth knowing about

- **VM hard-hangs during large unattended batch runs.** Root cause chain: FirmAE reuses one loop-mounted ext2/ext4 scratch device per image, mounted "unchecked" every time (no `e2fsck` between runs); both `batch.py`'s timeout handler and `firmae_runner.stop_run()` hard-kill QEMU on timeout without clean unmount; corruption compounds silently (dozens of `EXT4-fs error ... deleted inode referenced` kernel events over hours) until the guest kernel hangs completely; **no watchdog is configured on the VM**, so recovery requires an external Proxmox-side reset. Happened twice on large (900+ and 1116-image) `comprehensive` batch runs. Not yet mitigated — periodic `e2fsck -f` on the scratch device or a guest watchdog are the recommended (unimplemented) fixes. `batch.py` requires no manual resume bookkeeping either way — rerunning without `--force` auto-skips completed images and retries failed/timed-out ones.
- **Postgres outage, 2026-07-03 to 2026-07-09.** See §5, item 11. If Postgres appears down again: check `systemctl status postgresql@14-main.service` (not just the meta-unit `postgresql.service`, which reports "active (exited)" trivially and tells you nothing about the real cluster); check `journalctl -u postgresql@14-main.service`; if it shows the generic PID-file/protocol failure, try a manual `sudo pg_ctlcluster 14 main start` directly rather than trusting systemd's restart path, and check `/var/log/postgresql/postgresql-14-main.log` for the real recovery messages.

---

## 8. Open questions

- True emulation success rate across the full ~1116-image corpus (only fragmentary batches measured so far; the comprehensive run is what will finally answer this).
- Whether the VM-freeze pattern will recur again before a watchdog/fsck mitigation is implemented (it has now recurred twice).
- Whether default-credential testing produces reliable positives/negatives at scale, or mostly negatives due to the login-path coverage gap.
- Whether IP cameras behave systematically differently from routers in emulation success/failure patterns.
- Comparison of this framework's measured emulation success rate against FirmAE's own published ~80% baseline.

---

## 9. What the dissertation needs from this framework's output

- Emulation success rate, broken down by vendor and architecture.
- Vulnerability detection accuracy (precision/recall on a labelled subset).
- Mean processing time for fresh (non-cached) runs, broken down by profile.
- Honest accounting of the limitations in §6 — failed emulations, matcher false negatives, credential coverage gaps.
- Comparison to FirmAE's published baseline.

---

## 10. Quick orientation for running it

```bash
cd ~/project/framework
docker compose up -d                      # Valkey, optional but recommended
.venv/bin/python3 run.py <firmware_path> <brand> [profile]      # single image
.venv/bin/python3 batch.py ~/project/firmware/ [profile] [--vendor X] [--limit N] [--force]
```

Profiles: `fast` (top 100 ports), `comprehensive` (all 65535 ports), `stealth` (SYN, slow timing). Batch auto-skips images with an existing report; use `--force` to re-run. Reports land in `framework/reports/<firmware>-<run_id>.json`; batch summaries in `framework/reports/_summaries/batch-<timestamp>.json`.
