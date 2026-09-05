import sys
from pathlib import Path
sys.path.insert(0, '/root/project/framework')
import config
from batch import run_one, write_batch_summary

half_file = sys.argv[1]  # /root/half_a.txt or /root/half_b.txt

entries = []
with open(half_file) as fh:
    for line in fh:
        v, f = line.strip().split('|', 1)
        entries.append((v, Path(f)))

print(f"[*] Parallel half-run ({half_file}): {len(entries)} images")
summaries = []
for i, (vendor, path) in enumerate(entries, 1):
    print(f"\n[*] Image {i}/{len(entries)}")
    summaries.append(run_one(vendor, path, "comprehensive"))

write_batch_summary(summaries, "comprehensive")
print("\n[*] HALF RUN COMPLETE")
n_success = sum(1 for s in summaries if s['status']=='success')
n_failed  = sum(1 for s in summaries if s['status']=='emulation_failed')
n_timeout = sum(1 for s in summaries if s['status']=='timeout')
print(f"success={n_success} emulation_failed={n_failed} timeout={n_timeout}")
