# FirmAE 4-VPC Firmware Analysis — Final Summary

Generated: 2026-08-30. Updated later the same day after the VPCs were
restarted for one further "last pass" retry round (see below); the fleet
was left running for the user to tear down manually.

## Corpus overview

- **Total images tracked:** 1,113
- **Success:** 362 (32.5%)
- **Emulation failed:** 261 (23.5%)
- **Timeout:** 490 (44.0%)

These numbers reflect the corpus after multiple retry rounds this session:
an initial full-fleet pass, a 37-image "pending" backlog pass, a 45-image
camera-vendor pass (dlink/tplink/trendnet IP cameras, first time ever run),
an extended-timeout retest of 53 hand-picked "clean" images, a 46-image
pending/camera retry, a corpus-wide retry of 481 timeout-status images,
and finally a 120-image "last pass" of `emulation_failed` images that were
not confirmed dead ends (boots_no_confirmed_ip + interrupt_panic + other
non-deterministic failures).

## Last pass (2026-08-30, post-restart) — 120 images

The ~100–150 `emulation_failed` images flagged as "worth one more retry"
in the first version of this summary were run after the VPCs were restarted:
120 images (`worth_retrying=True`, confirmed dead ends excluded), split
10 per worker across all 12 panes, forced fresh extraction
(`use_cache=False`), normal 900s timing.

**Result: 34 recovered to success / 70 still emulation_failed / 16 timeout
(28.3% recovery).** All 34 came back with full probe output (services,
CVEs, web findings) — genuine first-pass-quality successes, not partials.
Recoveries skewed to Linksys `FW_EA*` routers, ASUS `FW_RT_*`, Netgear
`WNAP320`, and TP-Link `Archer_C8`/`RE305` — consistent with the
established "these families are non-deterministic / just needed a fresh
attempt" pattern rather than any code change. The 70 that failed again
mostly repeated their prior signature.

This is the last retry round; nothing further is queued.

## Failure taxonomy discovered this session

All of these were root-caused by reading actual serial console logs, not
guessed from status codes alone:

1. **`time_zone_panic` (confirmed dead end, ~110+ images)** — Netgear
   ACOS-derived devices panic with `exitcode=0x00001600` (exit(22)/EINVAL)
   after an NVRAM key (`time_zone` or `time_zone_x`) reads back `"0"`.
   A candidate fix (widening `fixImage.sh`'s path check for
   `libacos_shared.so`) was tried and **disproven** via a clean extended
   local retest — the override fires correctly but doesn't stop the panic.
   Root cause remains unresolved.

2. **`sem_key_variant` (confirmed dead end)** — `"Unable to get semaphore
   key!"` + the same `exitcode=0x00001600` panic. Confirmed across D-Link,
   ASUS, and Netgear devices. May share a root cause with #1 (both are
   NVRAM-key-read failures under semaphore issues) — flagged but not proven.

3. **`semaphore_livelock` (confirmed dead end)** — A busy-spin loop in
   `libnvram.so`'s NVRAM shim (`sem_get()`, no `sleep()` between 1000
   iterations) — rules out host-timing sensitivity as the cause. Genuinely
   deterministic, not a flaky race.

4. **`missing_hw_device_panic` (confirmed dead end)** — `exitcode=0x00008f00`
   preceded by `"open spiflash: No such device or address"` + `"Terminated"`.
   A missing/unsupported SPI flash device in the emulation.

5. **`interrupt_panic` (CONFIRMED NON-DETERMINISTIC)** — `"Kernel panic -
   not syncing: Fatal exception in interrupt"`, a genuine MIPS-level CPU
   exception. Seen repeatedly on TP-Link devices (Archer_C7 x2+,
   TL-WR841N_KR_V11, TL-WR847N_V8, DIR822B1, DIR-822_REVC). **Directly
   observed flipping between panic and clean boot on retries of the same
   image** — do not treat this signature alone as a dead end.

6. **Init-exec dead ends (two distinct sub-causes, same panic message)** —
   `"Starting init: /sbin/init exists but couldn't execute it (error -N)"`
   → `"Kernel panic - not syncing: No working init found"`.
   - **error -8 (ENOEXEC):** genuine exec-format mismatch with the vendor's
     own busybox binary.
   - **error -13 (EACCES):** despite the binary having correct `0755
     root:root` permissions — most likely FirmAE's own custom
     syscall-interception kernel patch (`firmadyne.syscall=1`) rejecting
     the `exec()` call. A kernel-patch-level issue, not a firmware problem.
     Confirmed on multiple camera images (D-Link DCS-69xx series).

7. **Device-emulation gaps (confirmed dead end, not worth retrying)** —
   `/dev/gpio: No such device` and `/dev/nvram: No such device`, spammed
   forever. Deterministic FirmAE limitations.

8. **Missing-reboot-binary loop** — vendor watchdog scripts (e.g.
   `mydlink-watch-dog.sh`) call `reboot`, which doesn't exist in the
   emulated environment, looping forever. Confirmed on multiple D-Link
   camera images.

9. **`boots_no_confirmed_ip` (the dominant non-panic category, ~650+
   images corpus-wide at peak)** — the device boots fully, runs real
   services, sometimes even `web_service=true` with an active webserver
   (`boa`, `lighttpd`, `httpd`), but check-mode's IP/service detection
   never confirms it. **Not a dead end** — many of these succeeded on a
   plain retry (`RE210`, `RE350`, `TL-WR902AC`, `DCS-934L`, `DCS-935L`,
   `NC220`, `DCS-5030L`, `DCS-960L`, and more).

## Two flagged-but-unfixed follow-up items (not pursued to a code fix)

- **`klogd` infinite socket-retry loop** — the kernel log daemon calling
  `sys_socket` 23,000–48,000+ times in a single boot, burning the entire
  check-mode window. Likely a FirmAE syscall-emulation gap specific to
  whatever socket type `klogd` requests.
- **Network-interface/VLAN naming mismatch** — `ifconfig`/`vconfig`/`route`
  failing with `"No such device"`, often paired with `devfs` mount
  failures, plus `iptables` calls using a `"flush"` argument syntax
  FirmAE's shim doesn't accept. The single largest marker across the
  deep audit (292 hits) — highest-ceiling fix candidate, but requires
  deeper work in FirmAE's own network-setup scripts.

## Extended-timeout finding (a real, validated result)

53 images with genuinely clean boot logs (no error marker, no device gap,
no repeating loop) were re-run with `firmae_runner._CHECK_TIMEOUT` and
`batch._WHOLE_RUN_TIMEOUT` both doubled (1800s / 2700s instead of
900s / 1500s).

**Result: 22 of 53 succeeded (41.5%)** — full probe results (services,
CVEs, web findings), not a fluke. These were never broken; the normal
900s window just wasn't long enough. The pattern skewed toward ASUS
`FW_RT_AC*`/`FW_RT_N*` routers and Netgear `JNR1010` variants — a
device-family boot-speed issue under QEMU/TCG, not a corpus-wide bug.

**Practical implication:** the default 900s check-mode timeout may be
systematically too short for a meaningful slice of the whole corpus, not
just these 53 hand-picked images.

## Infrastructure fixes made this session

- **SIGALRM whole-run watchdog** (`batch.py`) — a total wall-clock ceiling
  around each image's full pipeline (extraction + boot + probe stages),
  since individual per-stage timeouts didn't prevent silent multi-hour
  hangs from a stuck in-process socket.
- **Scoped process cleanup** (`firmae_runner.py`) — replaced blanket
  `pkill qemu-system` with per-image-scoped kills, fixing a bug where
  concurrent parallel images were killing each other's in-progress work.
- **Legacy-text-aware `worth_retrying` filter** — a recurring bug this
  session where free-text legacy values (`"Yes - worth one retry..."`)
  were silently excluded from retry-list building; fixed to interpret
  `Yes*`/`No*` prefixes correctly.

## What's backed up, and where

| What | Location |
|---|---|
| Master tracking CSV (final state) | `framework/image_tracking.csv` |
| Complete reports, all 4 VPCs | `framework/reports_vpc{1,2,3,4}_final/` |
| Postgres DB dumps, all 4 VPCs | `framework/db_backups/vpc{1,2,3,4}_firmware.sql` |
| Scratch directory listings (record only, not full data) | `framework/scratch_listing_vpc{1,2,3,4}.txt` |
| Full failure-diagnosis notes | `notes/vpc-run-failure-diagnoses.md` |
| This summary | `framework/FINAL_SUMMARY.md` |

The reports / DB dumps / scratch listings above were re-aggregated after the
last pass (2026-08-30). The raw scratch data (QEMU disk images, extracted
filesystems, full serial logs per image) is being uploaded separately to
Google Drive (tar.gz per VPC) before teardown; it is not in this repo.

The 4 VPCs were left **running** after the last pass for the user to tear
down manually (not powered off automatically this time).

## Open items for future work (not started)

- The `klogd` and network-interface-mismatch investigations (see above).
- The unresolved `time_zone`/`sem_key_variant` root cause — the one
  concrete lead (the `fixImage.sh` path fix) was tried and disproven.
