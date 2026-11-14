#!/usr/bin/env bash
# Build a postmarketOS-style boot.img for courbet using the mainline-courbet kernel.
#
# Combines:
#   - mainline Linux 6.17 Image.gz (+ DSI/DSC display patches) from mainline-courbet
#   - courbet DTB (sm7150-xiaomi-courbet.dtb)
#   - Alpine minirootfs initramfs with the mainline-courbet init
#   - pmos-courbet device metadata (deviceinfo)
#
# Output: boot-pmos.img — test with: fastboot boot boot-pmos.img
#
# Requires: python3, the repo checked out, and a previously unpacked work dir
#           (see scripts/local-boot-edit.py unpack).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${1:-$REPO_ROOT/../out/boot-work}"
OUT="${2:-$REPO_ROOT/../out/boot-pmos.img}"

if [ ! -d "$WORK" ]; then
    echo "Work dir $WORK not found. Run first:"
    echo "  python scripts/local-boot-edit.py unpack boot.img $WORK"
    exit 1
fi

# Repack using the local boot editor (header v2, gzip kernel, separate DTB section).
python "$REPO_ROOT/scripts/local-boot-edit.py" repack "$WORK" "$OUT"

echo "Built $OUT"
echo "Test it: fastboot boot $OUT"
