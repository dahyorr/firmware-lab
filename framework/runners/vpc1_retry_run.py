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

print(f"[*] VPC-1 retry run (force fresh, no cache): {len(entries)} images")
summaries = []
for i, (vendor, path, old_iid, old_status) in enumerate(entries, 1):
    print(f"\n[*] Retry {i}/{len(entries)}  (previously: {old_status}, old scratch id {old_iid})")
    summaries.append(run_one(vendor, path, "comprehensive"))

write_batch_summary(summaries, "comprehensive")
print("\n[*] VPC-1 RETRY RUN COMPLETE")
n_success = sum(1 for s in summaries if s['status']=='success')
n_failed  = sum(1 for s in summaries if s['status']=='emulation_failed')
n_timeout = sum(1 for s in summaries if s['status']=='timeout')
print(f"success={n_success} emulation_failed={n_failed} timeout={n_timeout}")
