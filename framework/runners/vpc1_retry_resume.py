import sys
from pathlib import Path
sys.path.insert(0, '/root/project/framework')
import config
from src import firmae_runner, orchestrator
from batch import run_one, write_batch_summary, derive_brand

# Force a genuine fresh check for every image - these all have a cached
# image_id from their previous failed/timed-out attempt, and use_cache=True
# (the default) would just return that stale result instantly instead of
# actually retrying.
_orig_check = firmae_runner.check
def _check_no_cache(*args, **kwargs):
    kwargs['use_cache'] = False
    return _orig_check(*args, **kwargs)
firmae_runner.check = _check_no_cache
orchestrator.firmae_runner.check = _check_no_cache

entries = []
with open('/root/vpc1_retry_failed.txt') as fh:
    for line in fh:
        vendor, path, old_iid, old_status = line.strip().split('|', 3)
        entries.append((vendor, Path(path), old_iid, old_status))

# Resume from retry #56 (index 55) onward - retries 1-55 already completed
# before the batch hung on PR2000 (retry #56), which hit a whole-pipeline
# in-process socket hang (SYN-SENT to the emulated device's own IP,
# survived 40+ min despite every individual stage timeout being set).
# batch.py now has a SIGALRM whole-run watchdog guarding against exactly
# this, so PR2000 is retried here too rather than skipped.
RESUME_FROM = 55  # 0-indexed
entries = entries[RESUME_FROM:]

print(f"[*] VPC-1 retry RESUME (force fresh, no cache, watchdog-protected): {len(entries)} images remaining")
summaries = []
for i, (vendor, path, old_iid, old_status) in enumerate(entries, RESUME_FROM + 1):
    print(f"\n[*] Retry {i}/161  (previously: {old_status}, old scratch id {old_iid})")
    summaries.append(run_one(vendor, path, "comprehensive"))

write_batch_summary(summaries, "comprehensive")
print("\n[*] VPC-1 RETRY RESUME COMPLETE")
n_success = sum(1 for s in summaries if s['status']=='success')
n_failed  = sum(1 for s in summaries if s['status']=='emulation_failed')
n_timeout = sum(1 for s in summaries if s['status']=='timeout')
print(f"success={n_success} emulation_failed={n_failed} timeout={n_timeout}")
