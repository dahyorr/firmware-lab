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

