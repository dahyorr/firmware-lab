SCRATCH_DIR = "/root/project/tools/FirmAE/scratch"

with open("/root/DEVICE_CHECK_INPUT") as f:
    for line in f:
        iid, filename = line.strip().split("|", 1)
        log_path = f"{SCRATCH_DIR}/{iid}/qemu.initial.serial.log"
        try:
            with open(log_path, "r", errors="replace") as lf:
                content = lf.read()
        except FileNotFoundError:
            print(f"{iid}|{filename}|NO_LOG")
            continue

        has_nvram_gap = "/dev/nvram: No such device" in content
        has_gpio_gap = "/dev/gpio: No such device" in content

        if has_nvram_gap and has_gpio_gap:
            tag = "BOTH_DEVICE_GAPS"
        elif has_nvram_gap:
            tag = "NVRAM_DEVICE_GAP"
        elif has_gpio_gap:
            tag = "GPIO_DEVICE_GAP"
        else:
            tag = "NO_DEVICE_GAP"
        print(f"{iid}|{filename}|{tag}")
