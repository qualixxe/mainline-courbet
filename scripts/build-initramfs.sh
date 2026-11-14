#!/usr/bin/env bash
# Build the aarch64 bring-up initramfs. Run as root (file ownership in the cpio
# archive must be root, and the kernel runs /init from it as PID 1).
#
# usage: build-initramfs.sh <rootfs-dir> <out.cpio.gz> [kernel-build-dir] [firmware-dir]
set -euo pipefail

ROOT="${1:?rootfs dir}"
OUT="${2:?output cpio.gz}"
KDIR="${3:-}"
FWDIR="${4:-}"

ALPINE_VER=3.21.9
ALPINE_URL="https://dl-cdn.alpinelinux.org/alpine/v3.21/releases/aarch64/alpine-minirootfs-${ALPINE_VER}-aarch64.tar.gz"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

# courbet's bootloader loads the ramdisk at 0x01000000 and the dtb at 0x01f00000,
# so the compressed ramdisk has to stay under 15 MiB. The DSP/venus/wlan blobs are
# ~27 MiB of that and none of them are needed to reach a shell, so they stay out
# until audio/camera/modem are actually brought up. modem.mbn is another 62 MiB of
# carrier configs.
SLIM_EXCLUDES=(
	--exclude 'modem.mbn' --exclude 'modem_pr'
	--exclude 'adsp.mbn' --exclude 'cdsp.mbn' --exclude 'venus.mbn'
	--exclude 'wlanmdsp.mbn'
	--exclude 'adspr.jsn' --exclude 'adsps.jsn' --exclude 'adspua.jsn'
	--exclude 'cdspr.jsn'
)

rm -rf "$ROOT"
mkdir -p "$ROOT"

echo "::group::Alpine minirootfs ${ALPINE_VER}"
curl -fsSL --retry 3 -o /tmp/alpine-minirootfs.tar.gz "$ALPINE_URL"
tar xzf /tmp/alpine-minirootfs.tar.gz -C "$ROOT"
echo "::endgroup::"

install -m 0755 "$HERE/initramfs/init" "$ROOT/init"
mkdir -p "$ROOT/tmp" "$ROOT/run" "$ROOT/config" "$ROOT/lib/firmware"

if [ -n "$KDIR" ]; then
	echo "::group::modules"
	KREL="$(cat "$KDIR/include/config/kernel.release")"
	# CROSS_COMPILE is required here even though we only install: kbuild sets
	# STRIP = $(CROSS_COMPILE)strip, and without it INSTALL_MOD_STRIP runs the
	# host x86 strip over aarch64 .ko files and dies with "Unable to recognise
	# the format of the input file".
	make -C "$KDIR" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
		INSTALL_MOD_PATH="$ROOT" INSTALL_MOD_STRIP=1 modules_install
	depmod -b "$ROOT" -F "$KDIR/System.map" "$KREL"
	rm -f "$ROOT/lib/modules/$KREL/build" "$ROOT/lib/modules/$KREL/source"
	echo "installed modules for $KREL"
	echo "::endgroup::"
fi

if [ -n "$FWDIR" ]; then
	echo "::group::firmware"
	mkdir -p "$ROOT/lib/firmware/qcom/sm7150"
	if [ -d "$FWDIR/lib/firmware/qcom/sm7150/courbet" ]; then
		rsync -a "${SLIM_EXCLUDES[@]}" \
			"$FWDIR/lib/firmware/qcom/sm7150/courbet" \
			"$ROOT/lib/firmware/qcom/sm7150/"
	fi
	# The courbet dts asks for qcom/sm7150/xiaomi/courbet/... while the firmware
	# repo ships qcom/sm7150/courbet/... . Provide both paths.
	mkdir -p "$ROOT/lib/firmware/qcom/sm7150/xiaomi"
	ln -sfn ../courbet "$ROOT/lib/firmware/qcom/sm7150/xiaomi/courbet"
	# Anything not under the courbet subdir (board files, gpu zap).
	if [ -d "$FWDIR/lib/firmware/qcom" ]; then
		rsync -a --ignore-existing "${SLIM_EXCLUDES[@]}" \
			"$FWDIR/lib/firmware/qcom/" "$ROOT/lib/firmware/qcom/"
	fi
	echo "::endgroup::"
fi

# Adreno 618 loads its SQE microcode from qcom/a630_sqe.fw, which lives in
# linux-firmware rather than the courbet blob repo. Without it adreno_request_fw
# fails with -2 and the GPU never initialises.
echo "::group::gpu firmware"
mkdir -p "$ROOT/lib/firmware/qcom"
curl -fsSL --retry 3 -o "$ROOT/lib/firmware/qcom/a630_sqe.fw" \
	"https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain/qcom/a630_sqe.fw"
ls -la "$ROOT/lib/firmware/qcom/a630_sqe.fw"
echo "::endgroup::"

echo "::group::pack"
mkdir -p "$(dirname "$OUT")"
( cd "$ROOT" && find . -print0 | cpio --null -o -H newc --quiet | gzip -9 ) > "$OUT"
ls -la "$OUT"
echo "::endgroup::"