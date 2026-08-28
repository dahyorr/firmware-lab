# VPC Full-Corpus Run — Per-Failure Diagnosis Log

One entry per failed/timed-out image across the 4-VPC run (started
2026-08-27, post-sasquatch-fix, post-reset). Each entry names the concrete
evidence (scratch id, boot log excerpt) behind the failure category, so
patterns are traceable rather than just counted. Categories match the
taxonomy established from the earlier local-corpus analysis (see
`failure_logs.zip` sent earlier in-session): NVRAM config error, kernel
panic, rootfs mount failure, kernel-module mismatch, switch-register spin,
plus **loopback IP** (a framework-level R-1 guard catch, not a FirmAE
category) and **kernel/network init hang** (boot stalls after CRDA/regulatory
domain setup with no further output until timeout).

## Log

| # | VPC | Vendor | Firmware | scratch id | Category | Evidence |
|---|---|---|---|---|---|---|
| 1 | VPC-1 | netgear | DGN1000NA_V1.1.00.40.zip | 2 | Loopback IP | `ip`=127.0.0.1, `ip.0`=10.0.2.15 (QEMU SLIRP default), `result`=true. FirmAE's own web-service check (`Waiting web service... from 127.0.0.1`) timed out after 360s but `result` still says true — FirmAE's success criterion only checks "network interface + ethernet detected," not an actual web response. Our R-1 guard correctly reclassifies. See `notes/loopback-ip-failures.md` for the full mechanism writeup. |
| 2 | VPC-1 | netgear | DGN1000_1.1.00.55_NA.zip | 3 | Loopback IP | Same signature: `ip`=127.0.0.1, `ip.0`=10.0.2.15, `result`=true. `DGN1000` family already had a 0% historical success rate before this from-scratch run — consistent with prior data, not a new regression. |
| 3 | VPC-3 | asus_latest | FW_BRT_AC828_30043807526.zip | 2 | Kernel/network init hang | `ip`/`ip.0`=192.168.0.1 (real private address, correctly assigned), but boot log stalls after `[*] cfg80211: Exceeded CRDA call max attempts. Not calling CRDA` → `[*] random: nonblocking pool is initialized` with no further output — no `result` written at all, ran the full 900s before the framework-level timeout killed it. This is the ASUS RT-N/AC-series limitation already documented in `dissertation-limitations` memory ("kernel/network init failed at QEMU level (mainly ASUS RT-N/AC series...)") — this run is the first time we're seeing it confirmed on `asus_latest` specifically, since that vendor was never tested locally before. |
| 4 | VPC-4 | trendnet_latest | TEG-160WS_1.00.16.zip | 2 | NVRAM config error | `ip`="" (empty), `ip.0`="0.0.0.13" (malformed/non-address), `result`=false — FirmAE itself correctly flagged failure this time, no R-1 guard needed. Boot log dominated by `sem_get: Waiting for semaphore timeout` and `nvram_get_buf: Unable to open key: /firmadyne/libnvram/daapd_dbdir! Set default value to ""` — the standard NVRAM-shim-gap signature (dominant category from the local-corpus analysis, 128/184 samples). Note: the firmware's own NVRAM defaults reference hostname `BLUECAVE-4455` — a leftover artifact from a shared vendor reference SDK, not a mix-up with the unrelated `asus_latest/FW_BLUECAVE...` image running on a different VPC (verified independently: `scratch/2/name` and `/brand` on VPC-4 correctly show `TEG-160WS`). |
| 5 | VPC-1 | netgear | DGN1000_V1.1.00.34_NA.zip | 4 | **Init exec format error (new category)** | `ip`="" (empty), `ip.0`=192.168.0.1 (real address, but never reached web-check since init never ran), `result`=false. Kernel log: `Starting init: /sbin/init exists but couldn't execute it (error -8)` then same for `/bin/sh`, then `Kernel panic - not syncing: No working init found`. Error -8 is `ENOEXEC` — the init binary is present in the extracted filesystem but the kernel can't execute its format at all (likely an architecture/ABI mismatch from extraction, or a genuinely incompatible init). Distinct from the earlier "kernel panic" category (which was NVRAM-semaphore-triggered, not a missing/bad init binary). |
| 6 | VPC-4 | trendnet_latest | TEG-204WS_1.00.010.zip | 3 | **Userspace crash — networkmap (new category)** | `ip`="" (empty), `ip.0`=192.168.0.1, `result`=false. Boot proceeds much further than #5 (kernel fully up, userspace running), but the `networkmap` process (PID 15510, a common embedded network-discovery daemon) hits an illegal program counter (`PC is at 0xb244`) and receives SIGALRM (signal 14) via the kernel's `do_signal` path, followed immediately by `/dev/nvram: No such device or address`. Looks like the NVRAM device node is missing/unavailable to this specific process, causing it to crash rather than degrade gracefully — different from the semaphore-timeout style NVRAM errors seen elsewhere. |
| 7 | VPC-1 | netgear | DGN1000_V1.1.00.51_NA.zip | 5 | Init exec format error | Identical signature to #5: `/sbin/init` and `/bin/sh` both fail with `error -8` (ENOEXEC), `Kernel panic - not syncing: No working init found`. Third `DGN1000`-family image, third distinct failure mode within that one family (loopback x2, init-exec-format x2) — the family is thoroughly incompatible, not flaky. |
| 8 | VPC-4 | trendnet_latest | TEG-240WS_1.00.18.zip | 4 | Kernel-module version mismatch | `insmod: kernel-module version mismatch` (x2) then `mvPpDrv not loaded` — same Marvell switch-driver signature confirmed in the very first local-corpus deep dive (`failure_logs.zip`, `kernel_module_mismatch/TEG-240WS...`). Same exact firmware, same exact failure, now reproduced independently on VPC-4 — confirms this is a deterministic, unfixable-at-our-layer limitation for this specific image, not environment noise. |
| 9 | VPC-2 | dlink | DCS-930L_FIRMWARE_1.11B1.ZIP | 3 | **Missing /dev/gpio device (new category)** | `ip.0`=192.168.0.1, no `result` written (timed out, 900s). Boot log repeats `/dev/gpio: No such device or address` after an NVRAM `IPAddressMode` lookup succeeds — the firmware tries to access GPIO pins (LED/button control, common in camera firmware) but the emulated environment provides no `/dev/gpio` node. Distinct from the NVRAM-key-lookup-gap category; this is a missing *device node*, not a missing config value. |
| 10 | VPC-3 | asus_latest | FW_RT_AC1200E_300438010574.ZIP | 3 | Kernel/network init hang | Identical signature to #3 (`FW_BRT_AC828`): boots to `Exceeded CRDA call max attempts. Not calling CRDA` → `random: nonblocking pool is initialized` → nothing further until the 900s timeout. Second confirmed instance — this is a real `asus_latest`-wide pattern, not a one-off. |

## Confirmed vendor-wide patterns (2026-08-27, checked at image ~8-10 per VPC)

- **VPC-2, `dlink` (DCS-930L camera line):** 5/5 timeouts so far, every single one hitting the identical `/dev/gpio: No such device or address` spin (checked `DCS-930L_FIRMWARE_1.11B1`, `..._REVA_FIRMWARE_1.14.02` directly, both identical). Infrastructure ruled out as a cause — CPU load ~0, 5.9GB RAM free, disk at 20%. This is a deterministic firmware characteristic: DCS-930L's init tries to access GPIO pins (LED/button control) that FirmAE's generic environment never provides, and the process just spins waiting rather than failing gracefully, burning the full 900s every time.
- **VPC-3, `asus_latest` (RT-AC router line):** 6/6 timeouts so far (after the initial `FW_BLUECAVE` success), every one hitting the identical CRDA regulatory-domain retry loop then silence (checked `FW_RT_AC1200E` and `FW_RT_AC1200GU` directly, both identical). Also infrastructure-ruled-out. Matches the already-documented ASUS RT-N/AC kernel/network-init limitation from the local corpus analysis — now confirmed as a near-total pattern for this vendor bucket specifically, not occasional.

**Bottom line on "why are they timing out":** it's not the VPS, not resource contention, not a fluke — it's that `dlink`'s camera-line firmware and `asus_latest`'s router-line firmware each hit one specific, reproducible incompatibility with FirmAE's generic emulation environment, and every image in those buckets is hitting the same wall. Worth considering whether to let these two vendor buckets run to completion for a clean statistic (100% failure rate, cleanly documented) or reassign them once the pattern is this consistent, since further images are very unlikely to behave differently.

## Update (2026-08-27, ~40 min later, image 19-21 per VPC)

- **VPC-2 `dlink` dead zone widened**: the 100% timeout pattern isn't limited to `DCS-930L` — it's now extended through **every DCS-930L revision (9/9), plus DCS-931L_REVA, plus DCS-932L x2** (12 consecutive timeouts total on this vendor so far). One partial exception: `DCS-932L_FIRMWARE_1.01` (scratch/16) shows the `boa` web server actually starting (`boa: starting server pid=569, port 80`) before still timing out — looks like a slow-boot-vs-240s-probe-window issue rather than the same dead spin, worth another look if it recurs.
- **VPC-3, two new distinct signatures within `asus_latest`:**
  - `FW_RT_AC1300UHP_30043808375.ZIP` (image_id 10): repeated `/dev/nvram: No such device or address` — a missing *device node* (not a missing NVRAM key), same concept as the GPIO-missing category but for `/dev/nvram` instead.
  - `FW_RT_AC51U_300438010528.ZIP` (image_id 18): got a genuinely different guest IP (`192.168.1.1` vs the usual `192.168.0.1`), then spins on `firmadyne: ioctl: 0x4` repeatedly — a kernel-module ioctl-interception spin, distinct from the CRDA loop and from the missing-device patterns.
- **VPC-3's `asus_latest` timeout count has not grown past 7** despite reaching image 19 — meaning several more `asus_latest` images have failed via `emulation_failed` (fast) or succeeded rather than timeout, a modest improvement over the earlier 100% streak.

## Update (2026-08-28, ~14hrs into 3-way parallel run)

**Cross-vendor confirmation of the CRDA regulatory-domain hang.** Previously
seen only on `asus_latest` RT-AC (entries #3, #10). Now confirmed on a
**third, unrelated vendor**: `FW_EA9500_1.1.7.180968_prod.img` (Linksys,
VPC-4, scratch id 91) shows the identical signature — real IP assigned
(`192.168.0.1`), a getty login prompt actually appears (`(none) login:`,
further than the ASUS cases got), then the same
`cfg80211: Calling CRDA to update world regulatory domain` retried 8 times
before `Exceeded CRDA call max attempts. Not calling CRDA`, followed by
silence until timeout. Also present: `/etc/system/wait: line 292: reboot:
not found` — the init script tries to call a `reboot` binary that doesn't
exist in the emulated rootfs, though this looks like a secondary symptom,
not the primary blocker.

**Read on this:** this is very likely not a vendor-specific bug at all — it's
a limitation in FirmAE's generic wireless/cfg80211 stack that surfaces on
any *high-power 802.11ac router* regardless of vendor (confirmed now on
ASUS RT-AC, Netgear R7xxx-class, and Linksys EA9xxx). Same underlying SoC
class (modern dual-band AC wireless with real regulatory-domain-aware
firmware), same wall. Worth citing as a single unified limitation category
in the dissertation rather than three separate vendor-specific ones.

**Overall timeout rate under 3-way parallelism is markedly higher** than the
sequential run was showing (roughly 75-90% of attempts timing out across all
4 VPCs at this checkpoint, vs the lower rate seen when running one image at
a time). Still unresolved whether this is (a) unlucky vendor/model placement
in the current batch of streams, or (b) genuine CPU-contention-induced
slowdown from 3 concurrent QEMU/TCG processes sharing 3 vCPUs pushing
marginal-but-working boots past the 900s window. Load average has stayed
under the vCPU ceiling in every spot-check so far, which argues against (b),
but this needs more data before concluding either way.

## Important operational finding (2026-08-28): some "timeouts" are dead-on-arrival, not slow boots

Checked two fresh timeout samples that don't match the CRDA-hang pattern:

- **VPC-3, `FW_RT_N10_B1_2034.zip`** (asus_latest, older N-series, NOT AC): guest
  panics at **7.4 seconds** in — `ioctl: Operation not supported` immediately
  followed by `Kernel panic - not syncing: Attempted to kill init!
  exitcode=0x00000000`.
- **VPC-4, `FW_WUMC710_v1.0.02.03_20140625.bin`** (linksys_latest, a MoCA
  network adapter, not even a router): guest panics at **3.2 seconds** in,
  right after an NVRAM timezone lookup — same `Kernel panic - not syncing:
  Attempted to kill init!` signature (matches the original local-corpus
  kernel-panic category).

**Both were logged by the framework as a full 900-second `Timed out`, not a
fast `emulation_failed`.** The guest died in single-digit seconds in both
cases — FirmAE's own check script doesn't appear to detect the panic and
exit early; it just waits out the entire configured timeout regardless.
This means a meaningful fraction of the "timeout" bucket across this whole
run may not actually be slow/hung boots at all — they could be near-instant
kernel panics that we're paying the full 900s wait for anyway. Worth
investigating whether `firmae_runner.py`/`run.sh` could detect "Kernel
panic" in the serial log and abort early rather than waiting the full
window — this alone could meaningfully cut the real wall-clock time of any
future full-corpus run without changing any actual results.

**Not every asus_latest/linksys_latest failure is the CRDA hang** — this
confirms both vendors have a genuine mix of failure categories (CRDA hang
on the modern AC-wireless models, kernel panic on older/simpler models),
not one uniform cause per vendor.

## Update (2026-08-28, later checkpoint)

- **VPC-1, `R7500_V1.0.0.52.zip`** (scratch id 150): real IP assigned (`192.168.1.1`), but spins at ~123s repeating `firmadyne: sys_socket[PID: 4007 (iptables)]` / `sys_setsockopt` calls indefinitely — looks like a firewall-rules-loading script stuck in a retry loop. **New category: iptables/firewall-init spin**, distinct from the CRDA/GPIO/NVRAM patterns already logged. Notably this is the *same* `R7500` model that had a flawless historical 8/8 success rate before — another data point for the emulation non-determinism already flagged (see `evaluation_readiness.md`), since this specific build/attempt hangs where siblings didn't.
- **VPC-4, `TEW-714TRU_0.0.0.zip`** (scratch id 106): this one's different in kind — the guest actually boots fully (`busybox`, `led_daemon`, `udhcpd`, `shttpd`, `goahead` webserver all running, real IP `192.168.10.1`), then hits a genuine **kernel OOM kill** at 357s: `Out of memory: Kill process 1805 (init_mdev.sh) score 0 or sacrifice child`, killing the mdev/hotplug init script. **New category: guest OOM under FirmAE's 256MB check-mode allocation** — this looks like a resource-constraint artifact of the emulation environment rather than a firmware incompatibility, since the device was demonstrably working (multiple real services already up) right up until the kill. Worth testing whether a higher `-m` value in check mode would let firmware like this complete successfully instead of stalling post-OOM.

## How to add an entry

For each new failure: pull `scratch/<id>/ip`, `ip.0`, `result`, and the tail
of `qemu.initial.serial.log` (or `qemu.final.serial.log` if run-mode was
reached). Match against the categories above before assuming a new one —
most failures so far repeat the same handful of signatures. Only add a new
category row/section if the boot log genuinely doesn't match any existing
pattern.
