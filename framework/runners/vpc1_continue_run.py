import sys
from pathlib import Path
sys.path.insert(0, '/root/project/framework')
import config
from batch import run_one, write_batch_summary

entries = []
with open('/root/netgear_continue.txt') as fh:
    for line in fh:
        v, f = line.strip().split('|', 1)
        entries.append((v, Path(f)))

print(f"[*] VPC-1 continuing netgear: {len(entries)} images remaining")
summaries = []
for i, (vendor, path) in enumerate(entries, 1):
    print(f"\n[*] Image {i}/{len(entries)}")
    summaries.append(run_one(vendor, path, "comprehensive"))

write_batch_summary(summaries, "comprehensive")
print("\n[*] VPC-1 CONTINUATION COMPLETE")
n_success = sum(1 for s in summaries if s['status']=='success')
n_failed  = sum(1 for s in summaries if s['status']=='emulation_failed')
n_timeout = sum(1 for s in summaries if s['status']=='timeout')
print(f"success={n_success} emulation_failed={n_failed} timeout={n_timeout}")
