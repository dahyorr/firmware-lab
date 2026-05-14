# Lab Notebook

## Setup
- Date:
- **Host:** Proxmox VE on AMD Ryzen 5 PRO 5650GE, 40GB RAM
- **VM:** Ubuntu 26.04 LTS Server
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