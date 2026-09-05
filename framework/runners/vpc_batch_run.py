import sys
sys.path.insert(0, '/root/project/framework')
import config
from batch import discover_firmware, run_one, write_batch_summary

VENDORS = ['netgear']  # replaced per-VPC

entries = []
for vendor in VENDORS:
    entries.extend(discover_firmware(config.FIRMWARE_DIR, vendor_filter=vendor))

print(f"[*] Full-corpus run (from scratch): {len(entries)} images across vendors {VENDORS}")
summaries = []
for i, (vendor, path) in enumerate(entries, 1):
    print(f"\n[*] Image {i}/{len(entries)}")
    summaries.append(run_one(vendor, path, "comprehensive"))

write_batch_summary(summaries, "comprehensive")
print("\n[*] VPC BATCH RUN COMPLETE")
n_success = sum(1 for s in summaries if s['status']=='success')
n_failed  = sum(1 for s in summaries if s['status']=='emulation_failed')
n_timeout = sum(1 for s in summaries if s['status']=='timeout')
n_error   = sum(1 for s in summaries if s['status']=='error')
print(f"success={n_success} emulation_failed={n_failed} timeout={n_timeout} error={n_error}")
