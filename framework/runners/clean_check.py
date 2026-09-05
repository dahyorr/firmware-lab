import re
from collections import Counter

SCRATCH_DIR = "/root/project/tools/FirmAE/scratch"

KNOWN_LOOP_MARKERS = [
    "No such device",
    "Bad argument",
    "Unable to get semaphore key",
    "Waiting for semaphore timeout",
    "Unable to open key",
    "sysctl: error",
    "sysctl: unknown",
    "Kernel panic",
]

with open("/root/CLEAN_CHECK_INPUT") as f:
    for line in f:
        iid, filename = line.strip().split("|", 1)
        log_path = f"{SCRATCH_DIR}/{iid}/qemu.initial.serial.log"
        try:
            with open(log_path, "r", errors="replace") as lf:
                content = lf.read()
                lines = content.splitlines()
        except FileNotFoundError:
            print(f"{iid}|{filename}|NO_LOG")
            continue

        matched_markers = [m for m in KNOWN_LOOP_MARKERS if m in content]

        # detect generic repetition: any line (stripped of timestamp/PID) appearing
        # a large number of times signals a stuck loop even without a known marker
        normalized = Counter()
        for l in lines:
            # strip leading [ 123.456] timestamp and PID numbers to catch loops
            # even when only the PID changes each iteration
            norm = re.sub(r"\[\s*\d+\.\d+\]", "", l)
            norm = re.sub(r"PID:\s*\d+", "PID:#", norm)
            norm = norm.strip()
            if norm:
                normalized[norm] += 1
        max_repeat = max(normalized.values()) if normalized else 0
        top_repeated = normalized.most_common(1)[0][0] if normalized else ""

        if matched_markers:
            print(f"{iid}|{filename}|HAS_MARKER:{','.join(matched_markers)}")
        elif max_repeat >= 15:
            print(f"{iid}|{filename}|REPEATING_LOOP(x{max_repeat}):{top_repeated[:60]}")
        else:
            print(f"{iid}|{filename}|CLEAN")
