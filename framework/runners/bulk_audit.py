import sys
import re
sys.path.insert(0, '/root/project/framework')
import psycopg2
import config

SCRATCH_DIR = "/root/project/tools/FirmAE/scratch"

with psycopg2.connect(**config.DB_CONFIG) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id, filename FROM image")
        rows = cur.fetchall()

# keep the highest id per filename (most recent extraction/attempt)
latest_id = {}
for iid, fname in rows:
    if fname not in latest_id or iid > latest_id[fname]:
        latest_id[fname] = iid

def classify(log_path):
    try:
        with open(log_path, "r", errors="replace") as f:
            content = f.read()
    except FileNotFoundError:
        return "NO_LOG"

    code_m = re.findall(r"exitcode=0x[0-9a-f]+", content)
    code = code_m[-1] if code_m else None

    if "Unable to get semaphore key" in content and "Kernel panic" in content:
        return "sem_key_variant"
    if "Waiting for semaphore timeout" in content:
        return "semaphore_livelock"
    if "Fatal exception in interrupt" in content:
        return "interrupt_panic"
    if code == "exitcode=0x00001600":
        return "time_zone_family_panic"
    if code == "exitcode=0x00008f00":
        return "missing_hw_device_panic"
    if code and "epc" in content:
        return f"cpu_exception_panic({code})"
    if "Kernel panic" in content:
        return f"other_panic({code})"
    if "VFS: Cannot open root" in content:
        return "rootfs_mount_fail"
    if len(content.strip()) == 0:
        return "EMPTY_LOG"
    return "boots_no_confirmed_ip"

with open("/root/AUDIT_INPUT") as f:
    for line in f:
        vendor, filename, old_status = line.strip().split("|", 2)
        iid = latest_id.get(filename)
        if iid is None:
            print(f"{vendor}|{filename}|{old_status}|NO_ID|NO_LOG")
            continue
        log_path_initial = f"{SCRATCH_DIR}/{iid}/qemu.initial.serial.log"
        log_path_final = f"{SCRATCH_DIR}/{iid}/qemu.final.serial.log"
        result = classify(log_path_initial)
        if result == "NO_LOG":
            result = classify(log_path_final)
        print(f"{vendor}|{filename}|{old_status}|{iid}|{result}")
