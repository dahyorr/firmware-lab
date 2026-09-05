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

## CORRECTION (2026-08-28): the -m 512 memory bump was reverted - it made things worse

The `-m 256` → `-m 512` change to FirmAE's check-mode scripts (proposed after
the `TEW-714TRU` OOM finding above) was deployed live to all 4 VPCs. Success
rate collapsed almost immediately: comparing the ~136 images processed
across the fleet right after the change to the prior checkpoint, only 3
succeeded (2.2%), down from the ~24-30% baseline every stream had been
running at. **Reverted back to `-m 256` on all 4 VPCs and locally.**

**Working theory:** embedded router firmware frequently detects available
RAM at boot and configures partition tables, cache sizing, or driver
behaviour based on it. Doubling the memory to more than the real hardware
ever had likely confused that logic into hanging on firmware that would
otherwise have booted fine at the correct (lower) memory figure - the
opposite problem from the OOM case, but from the same root cause (FirmAE's
generic environment not matching the real device's actual resource profile).

**Lesson:** the OOM fix helped a handful of specific images (confirmed:
`TEW-714TRU` genuinely stopped OOMing at 512MB) but broke far more images
than it fixed once deployed broadly. This should have been validated against
a wider before/after sample - not just the one firmware that motivated it -
before rolling out fleet-wide. If revisiting this, a per-architecture or
per-firmware memory override would be safer than a global bump.

## VPC-1 retry pass (2026-08-28): confirms genuine non-determinism, rules out caching artifact

Retrying VPC-1's failed/timed-out images with a forced fresh check
(`use_cache=False`) against models with a **100% historical success rate**
(`R6300v2`, `R7900`, `R8000`, `R8500`) reproduces an identical kernel panic
on several of them: `Kernel panic - not syncing: Attempted to kill init!
exitcode=0x00001600` at ~1.6-1.8s, same signature across models.

Verified this is not a stale/corrupted extraction cache: each retry gets a
genuinely new image_id from FirmAE (e.g. `R8000-V1.0.3.36_1.1.25` was id 46
originally, id 191 on this retry), with real non-zero `time_extract`
(0.68s) and `time_image` (8.46s) values confirming a fully independent
fresh extraction - not a reused tarball. The panic recurs anyway.

**Conclusion: this is genuine run-to-run non-determinism in FirmAE/QEMU
rehosting**, not a caching or environment artifact we introduced. Same
firmware, fully independent extraction, different outcome. Worth citing
directly in the dissertation's limitations/evaluation-reliability section -
see `evaluation_readiness.md` for the earlier instance of this same
phenomenon (that entry can now be strengthened with this cleaner evidence).

Dead-end family images retried in the same pass (`DGN1000` variants) behave
exactly as expected - same panic, same family, no surprise there.

## Deep-dive (2026-08-28): "flaky R-series" panic is systemic, not random - likely a libnvram.so bug

Following on from the VPC-1 retry pass finding several previously-100%-success
Netgear AC-series models (`R6250`, `R7900`, `R8000`, `R8500`, `R6300v2`) now
panicking on retry, this was investigated in depth by re-running the exact
same failing images **locally**, in complete isolation from the VPC fleet
(separate `reports_isolated_retest/` output directory, forced fresh check
via `use_cache=False`, results never merged into the main corpus).

**Ruled out (with evidence):**
- **Host hardware/timing non-determinism.** Local runs on a dedicated AMD
  Ryzen 5 PRO 5650GE (6 real cores, no virtualization overhead) vs. VPC-1's
  3-vCPU cloud instance ("Intel Core Processor" - a hypervisor's generic
  vCPU model string, with IBRS/no-TSX mitigation overhead). If this were
  genuine QEMU/TCG timing-sensitivity from host speed/jitter, the two very
  different environments should produce different outcomes. They didn't -
  identical panic, byte-for-byte, on both.
- **Stale/corrupted extraction cache.** Each local retry got a genuinely new
  FirmAE image_id with real non-zero `time_extract`/`time_image` values,
  confirming a fully independent fresh extraction each time - not a reused
  or corrupted tarball.
- **A stray `libnvram.override` file forcing the bad value.** Mounted the
  actual boot image (`mount -o loop,offset=1048576` - MBR partition 1 starts
  at sector 2048) and checked `/firmadyne/libnvram.override/`: only 4 files
  present (`bs_trustedip_enable`, `filter_rule_tbl`, `rip_enable`,
  `rip_multicast`), no `time_zone` or `time_zone_x` override at all.

**Confirmed, byte-for-byte identical, across 3 different models
(`R6250`, `R8500`, `R7900`), on both VPC-1 and local:**
```
nvram_set_default: Loading from native built-in table: router_defaults ...
nvram_set: time_zone = "PST8PDT"          <- legitimate default gets set
... (hundreds more nvram_set calls for other keys) ...
nvram_set_default_image: Copying overrides from defaults folder!
nvram_get_buf: 
[NVRAM] 9 time_zone
nvram_get_buf: = "0"                       <- same key now reads back "0"
Kernel panic - not syncing: Attempted to kill init! exitcode=0x00001600
```
`exitcode=0x00001600` decodes as the kernel's `WIFEXITED` encoding
(`exit_code << 8`): high byte `0x16` = decimal **22**, i.e. a genuine
`exit(22)` call by the init binary - and 22 is the conventional `EINVAL`
errno value many C programs pass straight to `exit()`. So this isn't a
signal/crash death, it's the vendor's own init code deciding to bail out
with an "invalid argument" style error the moment it reads back `"0"`
instead of a real timezone string like `"PST8PDT"`.

**Working theory:** a bug in FirmAE's own `libnvram.so` NVRAM shim, not
vendor firmware complexity or true emulation randomness. `time_zone` is
correctly set once early on, then silently reverts to `"0"` after several
hundred more `nvram_set` calls pile up - consistent with a hash-table
collision or fixed-size-buffer overflow inside the shim once enough keys
have been written. This would explain why it's 100% reproducible across
multiple *different* Netgear AC-series models: they all share the same
ACOS-derived codebase and the same NVRAM-heavy init sequence, so they all
hit whatever internal limit `libnvram.so` has at roughly the same point.

**Update (2026-08-28): "hash collision" theory ruled out, root cause
located.** Read `libnvram.so`'s actual source
(`tools/FirmAE/sources/libnvram/nvram.c`, 857 lines) in full. NVRAM values
are stored as individual files under a semaphore-guarded tmpfs mount, not a
hash table - so a hash-collision or fixed-buffer-overflow mechanism inside
the shim itself is architecturally impossible. The `time_zone` write-to-"0"
is not the shim corrupting a value; it happens further up the stack.

The real mechanism: `fixImage.sh` has a pre-existing pattern for exactly
this device family -
```bash
if $BUSYBOX grep -sq "time_zone_x" /lib/libacos_shared.so; then
    echo "Creating default time_zone_x!"
    echo -n "0" > /firmadyne/libnvram.override/time_zone_x
fi
```
- checked the actual extracted rootfs for one of these ACOS-based images:
`libacos_shared.so` lives at `/usr/lib/libacos_shared.so`, not
`/lib/libacos_shared.so` (`/lib` is a real, populated directory in this
image - not a symlink - it just doesn't contain this file). The `grep -sq`
check therefore always fails silently for this device class, and the
`time_zone_x` override is never created - consistent with the mounted
image showing only 4 override files (`bs_trustedip_enable`,
`filter_rule_tbl`, `rip_enable`, `rip_multicast`), none of them
`time_zone` or `time_zone_x`, even though the *other* 4 fixups (checked
against `/usr/sbin/httpd` / `/sbin/acos_service`, both real paths) fire
correctly.

Working hypothesis for the causal chain: `time_zone_x` is a numeric
zone-code NVRAM key that ACOS's own userspace init derives the human-
readable `time_zone` string from. With `time_zone_x` never seeded (stuck
at whatever uninitialized/default value the vendor's own table walker
leaves it at), that derivation falls back to stringifying the raw code as
an error path, producing `"0"` - which the init binary then treats as
invalid input and calls `exit(22)` (`EINVAL`) on, i.e. the observed
kernel panic ("Attempted to kill init!"). This isn't independently proven
line-by-line inside closed-source vendor code, but it's the only
mechanism consistent with every piece of evidence gathered so far (paired
NVRAM key naming, path bug confirmed on-disk, override-copy timing,
100% reproducibility limited to this exact ACOS-derived codebase).

**Candidate fix tried and disproven (local test, 2026-08-28):**
`fixImage.sh`'s `time_zone_x` check was widened to test both paths:
```bash
if $BUSYBOX grep -sq "time_zone_x" /lib/libacos_shared.so /usr/lib/libacos_shared.so; then
```
Tested live against `R6300v2-V1.0.4.6_10.0.76.zip` (fresh extraction,
image_id 339, local isolated retest). Result: **the override now fires**
(`nvram_set: time_zone_x = "0"` appears in the serial log, which it never
did before) - confirming the path-mismatch diagnosis was real - **but the
panic still occurs, identically**:
```
nvram_set: time_zone = "PST8PDT"     <- correct, from native table
...
nvram_set: time_zone_x = "0"          <- override now fires (it didn't before)
...
nvram_set: time_zone = "0"            <- still gets clobbered
Kernel panic - not syncing: Attempted to kill init! exitcode=0x00001600
```
So the missing override was real but not sufficient: something
downstream still derives/writes `time_zone = "0"` regardless of whether
`time_zone_x` is present. The two-key derivation hypothesis is likely
still correct in shape, but the specific value ("0") this override
supplies is wrong for this device class - "0" is evidently not a
recognized zone code here, so whatever reads `time_zone_x` back falls
through to the same error path either way. Needs a *valid* zone code
(or a direct `time_zone` override, applied after whatever else is
clobbering it) rather than just presence of the file.

**Status: not fixed.** Left in place locally since it's provably harmless
(only widens which devices the override applies to) but **not deployed to
any VPC** - it does not resolve the crash, so there is nothing worth
rolling out yet. All 51 Netgear AC-series retries completed on VPC-1 so
far (R6250/R6300v2/R7000/R7900/R8000/R8500/R6400, using the *unpatched*
script) show the byte-identical panic, confirming this remains 100%
deterministic and un-fixed pending further investigation into what
actually derives `time_zone` from `time_zone_x` and why "0" specifically
triggers the vendor's own `exit(22)` bailout.

**Local isolated retest complete (2026-08-28), conclusive:** all 16
images finished - `success=0, emulation_failed=14, timeout=2`. Every
single AC-series image failed, including all those built *after* the
`fixImage.sh` path fix landed (19:11:35 UTC) - the fix had no effect on
the outcome for any of them. This closes out the "maybe it partially
helps some models" possibility: it doesn't, for any tested model. The 2
timeouts were the `DGN1000` variants (already a known separate dead-end
family, unrelated to `time_zone`). Conclusion: the bug remains 100%
un-fixed pending a real theory for what derives `time_zone` from
`time_zone_x` and why. Not pursuing this further right now without a new
lead - the `time_zone_x` override mechanism was the only concrete lead
available and it's now exhausted.

**Separately confirmed broader footprint:** the same panic has now also
been observed on first attempt (not a retry) for `WNR3500L`/`WNR3500Lv2`
on VPC-1's main batch - this bug is not confined to the "AC-series"
naming, it spans a wider swath of the ACOS-derived Netgear lineup.

**Revision (2026-08-29, VPC-2): the "time_zone must be the literal string
0" framing may be wrong.** `linux-lzma_DIR-604M_150227.trx` (a D-Link
device, not Netgear/ACOS) reads back a *valid* time_zone value -
`nvram_get_buf: = "KST-9"` - yet still panics with the exact same
`exitcode=0x00001600` (exit(22)/EINVAL) as every "0" case. This one also
shows a *different* semaphore failure mode than the busy-spin livelock
found on VPC-1's R7500: `sem_get: Unable to get semaphore key! Utilize
altenative key.. by SR` (the `ftok()` call itself failing, not a stuck
wait loop).

Working revised hypothesis: the actual trigger may not be the specific
string value of `time_zone` at all - it may be reading *any* NVRAM key
while the semaphore mechanism is in a degraded/failed state, and
`time_zone` (or whatever key happens to be read at that moment) is just
the point where the vendor's init code decides to bail with EINVAL. This
would mean the `time_zone`-panic family and the semaphore-livelock family
found separately are likely **the same underlying bug wearing two
different symptoms**, not two unrelated bugs. Not yet proven, but this is
now the leading theory and reopens the question of whether this is
fixable (a semaphore/IPC configuration issue is more plausible to fix than
a hardcoded bad NVRAM default was). Worth a real look before writing this
off as permanently dead - flagged, not yet investigated further.

**Also new (VPC-2, same batch):** `Archer_C7_US__v2_180114.zip` and
`Archer_C7_V1_141204_US.zip` (TP-Link) show a completely different crash:
`Kernel panic - not syncing: Fatal exception in interrupt` - a genuine
MIPS-level exception inside an interrupt handler (timer/irq_exit/sprintf
in the trace), unrelated to NVRAM entirely. Only 1-2 data points so far,
not yet confirmed deterministic. Distinct from every other bucket - a
fifth failure category.

**Update (2026-08-29, VPC-2 pane a): the sem_key_variant signature is now
confirmed repeating, not a one-off.** 4 more D-Link devices in this batch
show the exact same "Unable to get semaphore key!" + exitcode=0x00001600
signature as `DIR-604M_150227.trx` found an hour earlier:
`DIR-550A_v1.10KRb09.trx`, `DIR-550A_v2.00b01.trx`,
`DIR-604M_FW2.00KR.trx`, `DIR-604M_v1.10KRb08.trx`. That's 5 D-Link
devices total now sharing this pattern - this is a real, repeating bug
class, not noise. Strengthens the case for actually investigating the
revised theory (same root cause as time_zone, different semaphore failure
path) rather than treating it as a curiosity.

**Pending/camera retry round (2026-08-29): interrupt_panic confirmed
non-deterministic.** Retried `Archer_C7_US`/`Archer_C7_V1` (previously
hit "Fatal exception in interrupt") - both came back with a completely
clean boot this time, no panic at all. `TL-WR841N_KR__V11` re-confirmed
the same panic on its retry, so it's not uniformly non-deterministic
across every device, but Archer_C7 specifically is not a reliable dead
end - don't classify it as worth_retrying=False purely on this signature
without checking whether it's this specific device family. 10 of 46
images succeeded on a plain retry (normal 900s timeout) in this round,
including 3 "boots_no_confirmed_ip" cases (`RE210`, `RE350`,
`TL-WR902AC`) succeeding outright with no extended timeout needed at all -
some of these just needed ANY fresh attempt, not necessarily more time.

**Extended-timeout retest result (2026-08-29): 22 of 53 succeeded - a real,
significant finding.** The 53 images flagged as "genuinely clean" in the
deep audit (no error marker, no device gap, no repeating loop in their
logs) were re-run from scratch with `firmae_runner._CHECK_TIMEOUT` and
`batch._WHOLE_RUN_TIMEOUT` both doubled (1800s / 2700s instead of
900s / 1500s). Result: **22 success, 28 still failed, 3 still timed out
even at the doubled ceiling** (41.5% success rate).

This confirms the core hypothesis: these 22 images were never actually
broken - they were failing purely because check-mode's normal 900s window
wasn't long enough for them to finish booting and get detected. All 22
came back with full probe results (services, CVEs, web findings) exactly
like a normal first-pass success - not a fluke.

The pattern skews strongly toward ASUS `FW_RT_AC*`/`FW_RT_N*` routers and
Netgear `JNR1010`/`jnr1010` variants (roughly a dozen of the 22
successes), suggesting these specific families just have a slower boot
sequence under QEMU/TCG than the 900s default assumes - not a device-class
bug, a timing-budget one. The 28 that still failed under double time
mostly repeat their original signature (same panic/pattern), confirming
those genuinely are dead ends, not timing-sensitive. 3 timed out even at
1800s - worth a look if pursued further, but low priority given the small
count.

**Practical implication:** the default 900s check-mode timeout may be
systematically too short for a meaningful slice of the corpus, not just
these 53. Worth considering whether to raise the default ceiling
project-wide (with a corresponding VPS-time cost) rather than only
applying it to hand-picked retries.

**Camera batch, first real data (2026-08-29, VPC-4, 9 of 45 images):**
0/9 succeeded. Corrects an earlier too-quick read ("wrong architecture") -
the `"Kernel panic - not syncing: No working init found"` message actually
covers at least two distinct causes with different errno values on the
`"Starting init: ... couldn't execute it"` line:
- **error -8 (ENOEXEC)**: genuine exec-format issue with the vendor's own
  busybox (4 of 9 images) - a real architecture/format mismatch.
- **error -13 (EACCES)**: despite the binary having correct `0755
  root:root` permissions (2 of 9 images) - this is NOT a filesystem
  permission problem. Most likely FirmAE's own custom syscall-interception
  kernel patch (`firmadyne.syscall=1`, confirmed active via the boot log's
  `execute: 1` flag) rejecting the `exec()` call itself. This needs kernel
  *patch source* investigation, not firmware-level inspection - out of
  reach for a quick log check.

Also found a third, genuinely new pattern (1 of 9): a MIPS CPU exception
followed by the vendor's own `mydlink-watch-dog.sh` looping forever on
`reboot: not found` - the emulated environment doesn't provide a `reboot`
binary the watchdog script depends on.

**One genuinely promising result**: `FW_TV-IP121WN` (TrendNet) shows
`web_service=true` (the `boa` webserver actively accepting connections -
`firmadyne: inet_accept[PID:... (boa)]`) but `ip=null` - check-mode's IP
detection simply never confirmed it, despite the device clearly being
network-functional. Exactly the kind of case the extended-timeout/
wider-probe test (stage 3) is meant to catch.

Remaining 1 of 9: timed out before an image ID was ever assigned
(extraction-stage failure, no scratch data to inspect).

**Follow-up investigation item (2026-08-29, not yet started):** deep audit of
the "boots but not confirmed reachable" bucket (651 images, the single
largest failure category across the whole corpus) found two concrete,
patchable-looking root causes worth a dedicated investigation once the
current corpus pass (pending backlog + cameras + extended-timeout retest)
is done:

1. **`klogd` infinite socket-retry loop.** Some images show the kernel log
   daemon calling `sys_socket` 23,000-48,000+ times in a single boot,
   burning the entire check-mode window without ever finishing init.
   Likely a FirmAE syscall-emulation gap specific to whatever socket
   type/protocol `klogd` requests. Single daemon, single syscall pattern -
   cheapest of the two to investigate.

2. **Network-interface/VLAN naming mismatch** (292 "No such device" hits
   from `ifconfig`/`vconfig`/`route`, often paired with `devfs` mount
   failures, plus 151 "Bad argument" hits from `iptables`/vconfig calls
   using syntax FirmAE's shim doesn't accept, e.g. the `flush` argument).
   Vendor init scripts expect specific VLAN sub-interfaces or devfs
   behavior FirmAE's guest network setup doesn't provide. Highest-ceiling
   fix (largest single marker across the whole audit) but a bigger lift -
   touches FirmAE's own network-setup scripts, not a one-line patch.

Ruled OUT as likely just noise, not real blockers: "Unable to open key"
(165 hits) and "sysctl: error" (26 hits) - the NVRAM shim already returns
a safe empty-string default on a missing key, and these mostly appear
once or a few times per log during ordinary startup, not as a repeating
loop like the two candidates above.

**Also new: a sixth failure category** - `NBG6604_V1.00_ABIR.3_C0.zip`
(ZyXEL) panics with `exitcode=0x00000004` alongside a full MIPS
register/PC dump (`epc`, `Cause`, `PrId`) - this looks like a genuine CPU
exception (likely SIGILL from the low-byte-only exit code encoding),
not the vendor's own clean `exit(EINVAL)` seen in every other panic
bucket so far. Only 1 data point - not yet confirmed deterministic.

**Update (2026-08-29, VPC-3 pane a retry results):**
- The `time_zone`/`exitcode=0x00001600` bug family is now confirmed
  broader than "reads `time_zone` back as 0" - 8 ASUS/Belkin devices in
  this batch hit the identical `exitcode=0x00001600` panic via a
  *different* NVRAM key (`time_zone_x` specifically, in at least one
  case) reading back "0". Same mechanism, different key - the classifier
  now needs to key off the exit code itself, not the specific NVRAM key
  name.
- `sem_key_variant` ("Unable to get semaphore key!") now confirmed on
  ASUS devices too, not just D-Link - broader footprint than first
  thought.
- **A seventh failure category**: 3 Belkin devices (`FW_WL_330N3G_1035`,
  `FW_WL_330N_1029`, `F9K1003_WW_1.00.42`) show `exitcode=0x00008f00`
  preceded by `open spiflash: No such device or address` and
  `Terminated` - looks like a missing/unsupported SPI flash device
  triggers a SIGTERM cascade to init dying. Not yet confirmed
  deterministic beyond this one batch.
- **Genuine retry successes found**: 4 ASUS devices (`FW_RT_AC53U`,
  `FW_RT_N10LX`, `FW_RT_N14UHP`, `FW_RT_N53`) succeeded on retry after
  originally timing out - confirms the retry strategy is finding real
  recoveries, not just re-confirming dead ends (6.3% success rate on
  this batch of 63).

**Dissertation framing:** this is a stronger, more precise story than plain
"emulation non-determinism" - it's a specific, traceable environment bug
with a concrete failure signature and a located root cause (a hardcoded
path assumption in FirmAE's own fixup script), evidenced across
independent hardware. Cite this deep-dive rather than the vaguer
non-determinism note in `evaluation_readiness.md` if writing about this
family's results.

## Last pass (2026-08-30, VPCs restarted): 34 of 120 emulation_failed images recovered on a plain fresh-extraction retry

After the fleet was powered off and the first `FINAL_SUMMARY.md` written, the
4 VPCs were restarted for one more round against the open item that summary
flagged: the `emulation_failed` images that were **not** confirmed dead
ends. List built as `status=emulation_failed AND worth_retrying=True`, minus
the confirmed-dead-end signatures (`time_zone_panic`, `sem_key_variant`,
`semaphore_livelock`, `missing_hw_device_panic`, the `/dev/gpio` and
`/dev/nvram` device-node gaps, the ENOEXEC init-exec cases). 120 images,
split 10 per worker across all 12 panes, forced fresh extraction
(`use_cache=False`), normal 900s check-mode timing.

**Result: 34 success / 70 still emulation_failed / 16 timeout (28.3%
recovery).** All 34 came back with full probe output (services, CVE
matches, web findings) identical in shape to a first-pass success - not
partials. New corpus totals: success 362 (32.5%), emulation_failed 261,
timeout 490.

**Which families recovered** (34): Linksys `FW_EA*` routers - 9
(`EA2700`, `EA4500V3`, `EA6200`, `EA6350V2`, `EA6700` x2, `EA6900`,
`EA9200` x2); ASUS `FW_RT_*` - 10 (`RT_AC55UHP`, `RT_AC66R`, `RT_AC66U`,
`RT_AC66W`, `RT_AC750GF`, `RT_N10U`, `RT_N10_1024`, `RT_N12C1`,
`RT_N12D1`, `RT_N12VP`); TrendNet - 4 (`TEW-411BRPplus`, `TEW-800MB`,
`TEW-811DRU`, `TEW-825DAP`); TP-Link - 5 (`Archer_C8_US` x2,
`Archer_C7_US__v2_180114`, `TL-WR841N_KR__V11`, `RE305_V1`); Netgear - 3
(`R6300v2-V1.0.3.28`, `WNAP320_V2.1.5`, `WNAP320_V2.1.6`); Belkin - 1
(`F9K1102_WW_3.04.13`); D-Link - 2 (`DIR822B1_FW202KRb05`,
`DCS-930L_REVA_FIRMWARE_1.16.04` - a camera image).

**Read on this: no code changed between the failing run and this one** -
same FirmAE, same scripts, same timeout, just a fresh extraction and
another attempt. So this is the same run-to-run non-determinism already
documented (`## VPC-1 retry pass (2026-08-28)`, `## Update (2026-08-29,
VPC-3 pane a retry results)`), now quantified at fleet scale: roughly a
quarter of the not-obviously-dead `emulation_failed` bucket is
recoverable purely by retrying. Two specific confirmations: `TL-WR841N_KR__V11`
and both `Archer_C8_US` images had previously shown the `interrupt_panic`
signature ("Fatal exception in interrupt") and were re-confirmed as
panicking on the 2026-08-29 retry round - this round they booted cleanly,
adding to the evidence that `interrupt_panic` is non-deterministic and
not a valid dead-end classifier on its own. The 70 that failed again
mostly reproduced their prior signature.

**Dissertation framing:** this is the cleanest single measurement of the
non-determinism problem in the whole project - a fixed 120-image set, one
variable (retry vs. no retry), 28% flip rate to success. Cite alongside
the `time_zone` deep-dive: that one is a *specific traceable bug*, this
one is the *statistical baseline rate* of spurious emulation failure.
Both matter for the evaluation-reliability section.

**Not pursued further.** This was explicitly the last retry round. The 70
still-failing and 16 timeout images were left as-is; the raw scratch data
for all 4 VPCs was archived to Google Drive (`gdrive:firmscan-scratch/`,
one `scratch_vpcN.tgz` per VPC) before the user tore the fleet down.

## How to add an entry

For each new failure: pull `scratch/<id>/ip`, `ip.0`, `result`, and the tail
of `qemu.initial.serial.log` (or `qemu.final.serial.log` if run-mode was
reached). Match against the categories above before assuming a new one —
most failures so far repeat the same handful of signatures. Only add a new
category row/section if the boot log genuinely doesn't match any existing
pattern.
