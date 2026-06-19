# IoT Firmware Security Analysis Framework — Overview

## What This Is

An automated dynamic analysis framework for IoT firmware. Given a firmware
image (ZIP or BIN), it emulates the firmware in a sandboxed QEMU environment
using FirmAE, then runs four analysis modules against the running virtual
device and produces a JSON report.

This is the implementation artefact for an MSc dissertation on IoT firmware
security at Leeds Beckett University.

---

## Architecture

```
firmware image
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  orchestrator.py — analyse_firmware()                       │
│                                                             │
│  1. acquisition   ── hash + validate the firmware file      │
│  2. firmae_runner ── FirmAE check mode (emulate & get IP)   │
│  3. firmae_runner ── FirmAE run mode (keep firmware live)   │
│  4. probe         ── nmap service scan                      │
│  5. cve_matcher   ── NVD API v2 lookup per service version  │
│  6. credential_tester ── HTTP Basic/POST + SSH login test   │
│  7. web_prober    ── admin paths, missing headers, banners  │
│  8. report        ── write JSON report                      │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
framework/reports/<firmware>-<run_id>.json
```

### Key source files

| File | Role |
|---|---|
| `framework/config.py` | All configurable paths and constants |
| `framework/run.py` | CLI for single firmware |
| `framework/batch.py` | CLI for a directory of firmware |
| `framework/src/orchestrator.py` | Pipeline — calls every module in order |
| `framework/src/firmae_runner.py` | FirmAE wrapper (check + run + stop + cache) |
| `framework/src/probe.py` | nmap service enumeration |
| `framework/src/cve_matcher.py` | NVD API v2 CVE lookup |
| `framework/src/credential_tester.py` | Default credential testing |
| `framework/src/web_prober.py` | Web interface fingerprinting |
| `framework/src/report.py` | JSON report writer |
| `framework/src/events.py` | Valkey pub/sub event bus (optional) |

---

## Prerequisites

1. **FirmAE** installed at `~/project/tools/FirmAE/`
2. **PostgreSQL** running with the `firmware` database and `firmadyne` user
   (created by FirmAE's installer)
3. **Python ≥ 3.10** and a virtual environment at `framework/.venv/`
4. **nmap** installed and on PATH
5. **sudo without password prompt** for FirmAE's QEMU/tap operations
   (configured by FirmAE's installer)
6. **Valkey** (optional — events are suppressed if unavailable):
   `cd framework && docker compose up -d`
7. An SSH route pinned to avoid conflict with FirmAE's 192.168.x.x tap
   interface (see lab-notebook.md §2026-05-15)

### Python dependencies

```bash
cd ~/project/framework
.venv/bin/pip install -r requirements.txt
# psycopg2-binary, valkey, requests, paramiko, python-nmap
```

---

## Analysis Profiles

| Profile | nmap flags | Use when |
|---|---|---|
| `fast` | `-F --open` (top 100 ports) | Batch runs; quick triage |
| `comprehensive` | `-sV -p-` (all 65535 ports) | Deep single-image analysis |
| `stealth` | `-sS -T2` (SYN, slow timing) | Minimise noise on host |

---

## How to Test Firmware

### Option A — Single image

```bash
cd ~/project/framework
.venv/bin/python3 run.py <firmware_path> <brand> [profile]
```

**Example:**

```bash
.venv/bin/python3 run.py \
  ~/project/firmware/dlink/DIR-868L_fw_revB_2-05b02_eu_multi_20161117.zip \
  dlink fast
```

The `brand` string is passed to FirmAE's `run.sh -c <brand>`. Use the vendor
name in lowercase (e.g. `dlink`, `netgear`, `tplink`).

**Output printed to terminal:**

```
[*] run_id : a3f2c1b8  status : success
      :53/tcp   domain   dnsmasq 2.62
      :80/tcp   http
      :22/tcp   ssh      Dropbear sshd 2011.54
[!] 30 CVE match(es)
[i] 5 web finding(s)
[*] Report : framework/reports/DIR-868L_fw_revB_2-05b02_eu_multi_20161117-a3f2c1b8.json
```

---

### Option B — Batch (directory of firmware)

Organise firmware into vendor subdirectories:

```
firmware_dir/
├── dlink/
│   ├── DIR-868L_fw_revB_2-05b02_eu_multi_20161117.zip
│   └── DIR-645_REVA_FIRMWARE_PATCH_v1.06B01_BETA02.zip
└── netgear/
    └── AC1450-V1.0.0.34_10.0.17.zip
```

Then run:

```bash
cd ~/project/framework
.venv/bin/python3 -u batch.py <firmware_dir> [profile] [--vendor <name>] [--limit N] [--force]
```

**Examples:**

```bash
# All firmware in the directory, fast profile
.venv/bin/python3 -u batch.py ~/project/firmware/ fast

# Only dlink, limit to 3 images
.venv/bin/python3 -u batch.py ~/project/firmware/ fast --vendor dlink --limit 3

# Re-run images that already have reports
.venv/bin/python3 -u batch.py ~/project/firmware/ fast --force
```

**Run in background (recommended for large batches):**

```bash
nohup .venv/bin/python3 -u batch.py ~/project/firmware/ fast > /tmp/batch.log 2>&1 &
echo "PID: $!"
tail -f /tmp/batch.log
```

The batch skips images that already have a report in `framework/reports/`.
Use `--force` to override.

A batch summary JSON is written to `framework/reports/_summaries/batch-<timestamp>.json`.

---

## Understanding the Output

### Report JSON structure

```json
{
  "firmware":    { "path", "name", "sha256", "size_bytes" },
  "timestamp":   "2026-06-17T13:37:26Z",
  "run_id":      "a3f2c1b8",
  "emulation": {
    "image_id":      163,
    "success":       true,
    "architecture":  "mipseb",
    "ip":            "192.168.0.1",
    "from_cache":    true
  },
  "probe": {
    "services": [
      { "port": 80, "protocol": "tcp", "service": "http", "version": "..." }
    ]
  },
  "cve_matches": [
    { "cve_id": "CVE-2017-14491", "cvss_score": 9.8, "severity": "CRITICAL",
      "port": 53, "service": "domain", "version": "dnsmasq 2.62" }
  ],
  "credentials": [
    { "port": 80, "username": "admin", "password": "admin",
      "success": true, "method": "http_post" }
  ],
  "web_findings": [
    { "port": 80, "path": "/admin", "finding_type": "exposed_admin",
      "severity": "medium" }
  ]
}
```

### Status values

| Status | Meaning |
|---|---|
| `success` | Emulation worked, all analysis modules ran |
| `emulation_failed` | FirmAE could not extract or boot the firmware |
| `timeout` | Firmware booted but never accepted connections within 600s |
| `error` | Unexpected exception in the pipeline |

### `from_cache: true`

FirmAE's PostgreSQL database stores prior check-mode results. When the same
firmware filename is seen again, the framework reuses that result and skips
the 8-15 minute extraction step. The `from_cache` flag in the report indicates
when this happened.

---

## Safety Rules (SPEC hard rules — always enforced)

- **R-1**: Non-private inferred IPs (anything outside RFC1918 / loopback)
  are never probed. The image is reclassified as `emulation_failed`.
- **R-3**: No exploitation. Credential testing only validates login — no
  post-authentication actions.
- **R-4**: No aggressive scanning. nmap profiles are bounded.
- **R-5**: Only emulated firmware is ever probed (no real devices).
- **R-18**: FirmAE runs are sequential, never parallel.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `emulation_failed` for all images | FirmAE check mode can't extract filesystem | Only certain MIPS/ARM firmware is supported by FirmAE |
| SSH drops during emulation | FirmAE's 192.168.x.x tap conflicts with your route to the host | See lab-notebook.md §2026-05-15 |
| Batch exits with code 143 / "Terminated" | `stop_run()` SIGTERM propagation bug | Already fixed in `firmae_runner.py` — ensure you have the latest version |
| `Valkey not reachable` | Valkey container not running | `cd framework && docker compose up -d`, or ignore it (events are optional) |
| Paramiko `IncompatiblePeer` tracebacks | Old firmware uses deprecated SSH KEX (e.g., Dropbear 2011) | Not a bug — credential testing still works, tracebacks are noise |
| `already_analysed` skips everything | Reports exist from prior runs | Use `--force` to re-run |
