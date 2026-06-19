# Lab Notebook

## Setup
- Date:
- **Host:** Proxmox VE on AMD Ryzen 5 PRO 5650GE, 40GB RAM
- **VM:** Ubuntu 22.04 LTS Server
  - 6 vCPU, CPU type `host` (AMD-V passthrough)
  - 12GB RAM (ballooning disabled)
  - 64GB disk (VirtIO SCSI, discard enabled)
  - Network: VirtIO on vmbr0
- **Access:** SSH from Windows workstation, key-based auth
- **Repo:** github.com/dahyorr/firmware-lab(private)

## Snapshots

| Name | Date | Description |
|---|---|---|
| base-installed | 2026-05-14 | Ubuntu 24.04 + Docker + base tools, before FirmAE |

---

## Log

## 2026-05-14 — Environment setup

**Goal:** Get the lab VM ready for firmware analysis work. Don't install FirmAE yet — just a clean, snapshotted base environment.

**What I did:**

1. Enabled nested virtualisation on the Proxmox host.
   - Verified with `cat /sys/module/kvm_amd/parameters/nested` → `1`
2. Created VM `firmware-lab` with the spec above.
3. Installed Ubuntu 24.04 Server. Notable choices:
   - Static IP assigned via router DHCP reservation (easier than configuring netplan).
   - LVM, no disk encryption.
   - OpenSSH server enabled at install time.
   - No snap packages.
4. SSH key auth set up from Windows workstation. No more password prompts.
5. Installed base toolchain via apt:
   - `git, curl, wget, vim, tmux, htop`
   - `build-essential, python3, python3-pip, python3-venv`
   - `qemu-utils, qemu-system-mips, qemu-system-arm`
   - `binwalk, nmap, net-tools`
6. Installed Docker CE from the official Docker apt repo (not the Ubuntu-bundled `docker.io`, which is older).
7. Added user to `docker` group, logged out and back in.
8. Verified:
   - `docker run hello-world` → success, no sudo needed.
   - `egrep -c '(vmx|svm)' /proc/cpuinfo` → 6, confirming AMD-V is visible inside the VM.
   - `binwalk --help` → tool present.
   - `qemu-system-mips --version` → present.
9. Created project directory structure under `~/project/`:
   - `firmware/` — raw firmware images (gitignored)
   - `tools/` — third-party tools, FirmAE etc. (gitignored)
   - `notes/` — this file and others
   - `results/` — outputs and evidence
   - `scripts/` — analysis scripts I write
10. Initialised git repo, set up `.gitignore` for firmware images and binaries, pushed to private GitHub.
11. Took Proxmox snapshot `base-installed`.

**Issues encountered:**

- None worth noting today. Everything installed cleanly.




## 2026-05-15 — First successful emulation

**Goal:** Reproduce FirmAE's baseline by booting a known-good firmware image.

**Result: SUCCESS.**

**Firmware tested:**
- D-Link DIR-868L revB firmware version 2.05b02 (EU multi)
- Filename: DIR-868L_fw_revB_2-05b02_eu_multi_20161117.bin
- SHA256: <run `sha256sum` and paste>
- Source: FirmAE GitHub releases v1.0

**Command:**
`sudo ./run.sh -c dlink_dir868l ./DIR-868L_fw_revB_2-05b02_eu_multi_20161117.zip`

**FirmAE output (final lines):**


## 2026-05-15 (later) — Network conflict between FirmAE and home network resolved

**Issue:** Running FirmAE in run mode (`-r`) caused SSH to drop. Diagnosis traced through three hypotheses (subnet collision, single-NIC limitation, host-route conflict) before identifying the actual cause.

**Root cause:** Home network topology — Windows client on 192.168.0.0/24, opnsense bridge at 192.168.0.3 routing to lab network 10.10.0.0/24, lab VM in 10.10.1.0/24. When FirmAE brings up its tap1_0.1 interface claiming 192.168.0.1/24 inside the VM, the kernel routing table gets a new, more-specific route for 192.168.0.0/24 via the tap interface. Reply packets to the SSH client at 192.168.0.11 then route into the emulated firmware instead of back to the client.

**Fix:** Pin a /32 route to the SSH client before the conflict appears:

`sudo ip route add 192.168.0.11/32 via 10.10.1.1 dev enp6s18`

Made persistent via a systemd oneshot service.

**Lesson:** FirmAE assumes the host has no traffic flowing through 192.168.0.0/24 because it hardcodes that subnet for emulated firmware. In any lab where the operator's access path also passes through 192.168.0.0/24, an override route is required. This is the kind of practical finding that would belong in a "deployment considerations" section of the dissertation.

**Significance for project:** This is the first real friction point between FirmAE as published and FirmAE as deployable in a typical research environment. Worth mentioning in the dissertation's implementation chapter as evidence that the integration work the project undertakes is more than packaging — it includes solving real interoperability issues.

**Time spent on this issue total:** roughly <X> hours across multiple sessions

## Findings from interactive probing — DIR-868L

Manual nmap -sV scan against the emulated firmware revealed six open ports across three distinct services:

- **Port 53/63481 (UDP/TCP DNS):** dnsmasq version 2.45. This is an outdated version (from 2008) with multiple documented CVEs in the National Vulnerability Database. This is the kind of finding the framework's CVE-matching module will surface automatically.
- **Port 80:** D-Link administrative web interface (custom "WebServer"). Page title "D-LINK", consistent with the genuine device interface.
- **Port 8181/8182:** D-Link SharePort web interface for shared storage and printing.
- **Port 49152:** likely UPnP daemon (common default port for IGD/UPnP).

The dnsmasq finding is a good first concrete demonstration of the value of the framework: a single service banner ("dnsmasq 2.45") immediately suggests multiple known vulnerabilities to investigate. This kind of automated identification is the core value proposition of the dynamic analysis module described in section 4.2.3 of the proposal.



## Design decision: cache detection rather than cache clearance

The framework detects when FirmAE has already processed a firmware image
and reuses the cached result instead of re-running. Detection happens by
querying FirmAE's PostgreSQL `image` table for the firmware filename,
then verifying that `scratch/<iid>/result` exists.

Rationale:
- Re-extraction is the most expensive step (~5-10 minutes); skipping it
  on repeat runs makes the framework usable iteratively
- Processing time measurements remain accurate (they describe the first
  run, not arbitrary re-runs)
- The `from_cache` flag in the report tells reviewers when a result is
  reused vs freshly produced

Alternative considered: always clear cache before runs (Strategy A).
Rejected because it discards useful data and adds 5-10 minutes per
re-run with no real benefit.



## 2026-06-17 — Batch run: 5 firmware across 3 vendors (v2 framework)

**Goal:** Demonstrate the complete v2 pipeline on 5+ firmware images from different vendors.

**Bug fixed during this session:** `stop_run()` in `firmae_runner.py` was sending `sudo kill -TERM -{pgid}` to FirmAE's process group. Despite Python having a different PGID, sudo's signal-forwarding behaviour propagated the SIGTERM back to the Python orchestrator, killing the batch process immediately after QEMU started. Fix: replaced process-group kill with a targeted `sudo kill -TERM {pid}` (killing only the specific sudo PID); `pkill` already handles QEMU and surviving sub-shells in the follow-up steps.

**Batch run results (fast profile, 3 vendors, from cache):**

| Firmware | Vendor | Arch | IP | Services | CVEs | Web |
|---|---|---|---|---|---|---|
| DCS-930L 1.08_B4 | dlink | mipsel | blocked | — | — | — |
| DCS-930L 1.09_B2 | dlink | mipsel | 192.168.0.1 | 4 | 0 | 0 |
| AC1450 V1.0.0.34 | netgear | armel | 192.168.1.1 | 5 | 10 | 13 |
| JNR1010 V1.0.0.24 | netgear | mipseb | 192.168.0.1 | 4 | 0 | 4 |
| ArcherC2 KR V1 | tplink | mipsel | 192.168.0.1 | 4 | 0 | 0 |
| Archer C7 US V4 | tplink | mipseb | 192.168.1.1 | 3 | 30 | 5 |

DCS-930L 1.08_B4 was rejected by R-1 (inferred public IP 2.65.87.200 — not probed).

**Notable findings:**

- **Netgear AC1450**: dnsmasq 2.15-OpenDNS-1 flagged with 10 CVEs (CVSS up to 7.8). Admin paths exposed: /admin, /cgi-bin/, /HNAP1/, /setup.cgi, /goform/, /webproc.
- **TP-Link Archer C7**: Dropbear SSH 2011.54 (2011 vintage) with 30 CVE matches (CVSS up to 7.5). dnsmasq 2.62 also present. SSH key exchange negotiation failed with modern paramiko (deprecated KEX algorithms: diffie-hellman-group1-sha1). 4 missing security headers.
- Paramiko produces noisy tracebacks for old SSH firmware (IncompatiblePeer); these are handled gracefully and don't affect results — worth suppressing with `logging.getLogger("paramiko").setLevel(logging.ERROR)`.

**Emulation success rate:** 5/5 (100%) for images with private IP, 6/6 total including the R-1 rejection.


## 2026-06-17 — Batch run 2: 5 firmware, dlink_latest + netgear_latest (fresh runs)

**Goal:** Extend batch coverage to 5 more firmware images not previously in the FirmAE database, requiring full check-mode extraction.

**Batch run results (fast profile, all fresh — from_cache=False):**

| Firmware | Vendor | Arch | IP | Services | CVEs | Web |
|---|---|---|---|---|---|---|
| DIR-645 REVA v1.06B01 | dlink_latest | — | emulation_failed | — | — | — |
| DIR-655 REVC v3.02.B05 | dlink_latest | — | emulation_failed | — | — | — |
| DIR-803 REVA v1.04.B02 | dlink_latest | mipseb | 192.168.0.1 | 4 | 0 | 0 |
| AC1450 V1.0.0.36 | netgear_latest | armel | 192.168.1.1 | 6 | 0 | 13 |
| EX6100 V1.0.2.24 | netgear_latest | mipsel | 192.168.0.1 | 4 | 0 | 0 |

**Total runtime:** 18.7 minutes (fresh extraction: ~8-15 min per successful image).

**Notable findings:**

- **Netgear AC1450 V1.0.0.36**: 6 services including FTP (Bftpd 1.6.6) and dnsmasq 2.15-OpenDNS-1. 13 web findings (same admin paths as V1.0.0.34: /admin, /cgi-bin/, /HNAP1/, /setup.cgi, /goform/, plus missing security headers). CVE count was 0 despite dnsmasq 2.15 being present — the "OpenDNS-1" suffix in the version string prevented NVD keyword matching. This is a false-negative case worth noting in the dissertation.
- **DIR-645 and DIR-655**: FirmAE extracted the kernel but failed to extract the root filesystem (`rootfs_extracted=false`, `kernel_extracted=true` in the `firmware` DB; `scratch/420/result` and `scratch/421/result` both read `extraction fail`). Without a rootfs FirmAE cannot build the disk image, so emulation cannot proceed. These are REVA/REVC variants; the older REVA v1.04.B13 and v1.06.B01 in the database (IDs 73/74) also failed extraction, suggesting the DIR-645 line uses a proprietary SquashFS variant or packing method that FirmAE's `extract.sh` does not handle. This is a documented FirmAE limitation — it supports standard SquashFS, JFFS2, and CramFS but not all vendor-customised packing schemes.
- **DIR-803 and EX6100**: Emulated successfully but nmap returned no versioned service banners, so CVE matching produced zero results. Consistent with firmware that doesn't serve identifiable version strings.

**Emulation success rate:** 3/5 (60%) for this batch; 2 D-Link images failed extraction.

**CVE false-negative note:** AC1450 v1.0.0.36 carries dnsmasq 2.15-OpenDNS-1 — the same base version that produced 10 CVE hits for v1.0.0.34 (where the version string was plain "2.15-OpenDNS-1"). The NVD keyword query used is the full version string; a production-quality matcher would strip vendor suffixes before querying.


## 2026-06-07 — V2 framework design decisions agreed

Decisions made while drafting SPEC.md, locked in for v2 development:

1. Valkey pub/sub in v1, not just v2. Modules publish status events to
   topics from day one; v1 has an optional subscriber that prints or
   ignores. v2's web wrapper attaches its own subscriber for live UI
   updates.

2. Configurable output paths everywhere. No hardcoded report directory.
   Orchestrator passes target paths into modules.

3. JSON as canonical report format. PDF generation is a separate module
   in reporting/ that consumes the JSON. Both run in v1.

4. Thin orchestrator. run.py parses arguments and calls analyse_firmware().
   Modules do the real work. v2 worker is just another caller of the
   same function.

Implication: v1 is not a throwaway prototype. It is the production logic
with the CLI as one entry point. v2 adds a web entry point but does not
replace the framework's internals.


