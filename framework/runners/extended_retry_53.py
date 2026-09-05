import sys
from pathlib import Path
sys.path.insert(0, '/root/project/framework')
import config
from src import firmae_runner, orchestrator
import batch
from batch import write_batch_summary

# Extend both the check-mode ceiling and the whole-run watchdog together -
# these 53 images looked like ordinary, error-free boots that just got cut
# off mid-stream by the normal 900s check-mode timeout. Doubling it gives
# them a real chance without risking an indefinite hang (still bounded).
EXTENDED_CHECK_TIMEOUT = 1800
EXTENDED_WHOLE_RUN_TIMEOUT = 2700
firmae_runner._CHECK_TIMEOUT = EXTENDED_CHECK_TIMEOUT
batch._WHOLE_RUN_TIMEOUT = EXTENDED_WHOLE_RUN_TIMEOUT

_orig_check = firmae_runner.check
def _check_no_cache(*args, **kwargs):
    kwargs['use_cache'] = False
    return _orig_check(*args, **kwargs)
firmae_runner.check = _check_no_cache
orchestrator.firmae_runner.check = _check_no_cache

entries = []
with open('/root/extended53_vpc1.txt') as fh:
    for line in fh:
        vendor, path, old_iid, old_status = line.strip().split('|', 3)
        entries.append((vendor, Path(path), old_iid, old_status))

print(f"[*] Extended-timeout retry: {len(entries)} images "
      f"(check_timeout={EXTENDED_CHECK_TIMEOUT}s, whole_run_timeout={EXTENDED_WHOLE_RUN_TIMEOUT}s)")
summaries = []
for i, (vendor, path, old_iid, old_status) in enumerate(entries, 1):
    print(f"\n[*] Retry {i}/{len(entries)}  (previously: {old_status}, old scratch id {old_iid})")
    summaries.append(batch.run_one(vendor, path, "comprehensive"))

write_batch_summary(summaries, "comprehensive")
print("\n[*] EXTENDED-TIMEOUT RETRY COMPLETE")
n_success = sum(1 for s in summaries if s['status']=='success')
n_failed  = sum(1 for s in summaries if s['status']=='emulation_failed')
n_timeout = sum(1 for s in summaries if s['status']=='timeout')
print(f"success={n_success} emulation_failed={n_failed} timeout={n_timeout}")
