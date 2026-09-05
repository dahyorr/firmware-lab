# VPC batch-run driver scripts

Ad-hoc runner scripts used on the 4-VPC fleet for the corpus run and its retry
rounds (Aug 27–30 2026). Pulled off VPC-1 before teardown so the methodology is
reproducible. Paths inside them are hardcoded to the VPC layout
(`/root/project/framework`, `/root/<name>_vpcN<pane>.txt` work lists).

All follow the same shape: prepend `framework/` to `sys.path`, optionally
monkeypatch `firmae_runner.check` to force `use_cache=False` (fresh extraction),
read a pipe-delimited work list (`vendor|path|old_image_id|old_status`), call
`batch.run_one(vendor, path, "comprehensive")` per image, then
`write_batch_summary`.

## Extended-timeout mechanism

`extended_retry_53.py` is the only script that changes the timeout ceilings.
The framework defaults (`firmae_runner._CHECK_TIMEOUT = 900`,
`batch._WHOLE_RUN_TIMEOUT = 1500`) are **unchanged in the repo**; this script
overrides them *at runtime* for one retry round:

```python
EXTENDED_CHECK_TIMEOUT     = 1800   # check-mode boot/detect ceiling (default 900)
EXTENDED_WHOLE_RUN_TIMEOUT = 2700   # SIGALRM whole-pipeline watchdog (default 1500)
firmae_runner._CHECK_TIMEOUT = EXTENDED_CHECK_TIMEOUT
batch._WHOLE_RUN_TIMEOUT     = EXTENDED_WHOLE_RUN_TIMEOUT
```

Result of that round: 22 of 53 "genuinely clean" images that had been failing
only on the 900s window succeeded at 1800s (see `FINAL_SUMMARY.md` and the
notes). The doubled values were **not** made the project default — reverted
after the round because a wider before/after sample was never taken.

## Script families (chronological)

| script(s) | round |
|---|---|
| `vpc_batch_run.py`, `vpc_half_run.py`, `vpc1_continue_run.py` | initial full-corpus pass |
| `vpc1_combined_run_{a,b,c}.py`, `vpc1{a,b,c}2_retry_run.py`, `vpc1_retry_run.py`, `vpc1_retry_resume.py` | first retry rounds |
| `pending_run_1.py` | 37-image "pending" backlog |
| `camera_run_vpc1{a,b,c}.py` | 45-image IP-camera vendor pass |
| `clean_check.py`, `device_gap_check.py`, `bulk_audit.py` | log-audit helpers (classify failures, find device-node gaps) |
| `extended_retry_53.py` | 53-image extended-timeout retest (1800/2700) |
| `pcretry_run_vpc1{a,b,c}.py` | 46-image pending/camera retry |
| `alltimeout_run_vpc1{a,b,c}.py` | corpus-wide retry of all 481 timeout rows |
| `lastpass_run_vpc1{a,b,c}.py` | 2026-08-30 last pass — 120 `emulation_failed` non-dead-ends, 34 recovered |

`worklists_vpc1/` holds the `.txt` inputs (and a few audit result dumps) these
scripts consumed, from VPC-1. Only VPC-1's copies were kept; the other panes'
lists were the same format, different slices.
