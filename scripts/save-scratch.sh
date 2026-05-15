mkdir -p ~/project/scripts
cat > ~/project/scripts/save-scratch.sh <<'EOF'
#!/bin/bash
# Save FirmAE scratch artefacts to results/baseline/<name>/
# Usage: ./save-scratch.sh <image_id> <name>
set -e

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <image_id> <name>"
    echo "Example: $0 1 dlink_dir868l"
    exit 1
fi

IID="$1"
NAME="$2"
SRC="$HOME/project/tools/FirmAE/scratch/$IID"
DST="$HOME/project/results/baseline/$NAME"

if [ ! -d "$SRC" ]; then
    echo "Error: $SRC does not exist"
    exit 1
fi

mkdir -p "$DST"

# Copy small text artefacts and logs (skip image/ and image.raw — too big)
for f in emulation.log qemu.final.serial.log qemu.initial.serial.log \
         ip architecture result web ping brand name \
         makeImage.log makeNetwork.log tar2db.log \
         fileList fileType current_init init \
         kernelCmd kernelInit kernelVersion isDhcp; do
    if [ -f "$SRC/$f" ]; then
        cp "$SRC/$f" "$DST/"
    fi
done

# Timing files
for f in "$SRC"/time_*; do
    [ -f "$f" ] && cp "$f" "$DST/"
done

echo "Saved scratch/$IID to results/baseline/$NAME"
ls "$DST"
EOF

chmod +x ~/project/scripts/save-scratch.sh