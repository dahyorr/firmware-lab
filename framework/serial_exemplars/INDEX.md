# Serial-log exemplars — one representative QEMU serial log per failure category

Pulled from the live VPC fleet (VPC-1/2/4) on 2026-08-30 before teardown, so the
nine-category failure taxonomy in `FINAL_SUMMARY.md` / `notes/vpc-run-failure-diagnoses.md`
is backed by primary evidence, not just prose.

Each `<category>/` holds:
- `EXCERPT.txt`     — appendix-ready: boot header + context around the signature line + final tail, with provenance
- `qemu.*.serial.log.gz` — the full serial log(s), gzipped
- `scratch_*`       — the scratch-dir metadata files (name, brand, arch, ip, ip.0, result)
- `PROVENANCE.txt`  — VPC, scratch id, firmware name/brand, matched regex

| category | firmware (exemplar) | key signature |
|---|---|---|
| time_zone_panic | Netgear R7000-V1.0.5.64_1.1.88 | `Kernel panic ... Attempted to kill init! exitcode=0x00001600` after NVRAM key reads back "0" |
| sem_key_variant | D-Link DIR-604M_FW2.00KR | `sem_get: Unable to get semaphore key! Utilize altenative key.. by SR` + same 0x00001600 panic |
| missing_hw_device_panic | Belkin F9K1103_WW_1.10.23 | `open spiflash: No such device` → `exitcode=0x00008f00` |
| interrupt_panic | TP-Link TL-WR841N_V11_150616 | `Kernel panic - not syncing: Fatal exception in interrupt` (MIPS irq handler) |
| init_exec_enoexec | Netgear DGN1000_V1.1.00.34_NA | `Starting init: /sbin/init ... couldn't execute it (error -8)` → No working init found |
| init_exec_eacces | D-Link DCS-6915_REVA_FIRMWARE_v1.11.00 | same but `(error -13)` despite 0755 root:root — syscall-interception reject |
| no_working_init | ZyXEL WRE6602_V1.00_ABKK.3_C0 | `Kernel panic - not syncing: No working init found` (second vendor/arch data point) |
| dev_gpio_gap | Netgear DGN2200_1.0.0.20 | `/dev/gpio: No such device or address` spun repeatedly |
| dev_nvram_gap | Netgear R7000-V1.0.3.56_1.1.25 | `/dev/nvram: No such device` |
| reboot_not_found | TP-Link Archer_C5400_US_V1_170731 | `/etc/rc.common: line 98: reboot: not found` looped by init/watchdog |
| crda_regdom_hang | Netgear WNDR3700v4_V1.0.1.52 | `cfg80211: Exceeded CRDA call max attempts. Not calling CRDA` then silence (802.11ac reg-domain) |
| boots_no_confirmed_ip | Netgear JR6150/R6050-V1.0.1.2 | webserver came up but check-mode never confirmed an IP |

VPC-3 was already torn down when these were pulled; its per-image reports and DB dump are still in the bundle.
