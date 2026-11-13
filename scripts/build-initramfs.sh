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
	make -C "$KDIR" ARCH=arm64 INSTALL_MOD_PATH="$ROOT" INSTALL_MOD_STRIP=1 modules_install
	depmod -b "$ROOT" -F "$KDIR/System.map" "$KREL"
	rm -f "$ROOT/lib/modules/$KREL/build" "$ROOT/lib/modules/$KREL/source"
	echo "installed modules for $KREL"
	echo "::endgroup::"
fi

if [ -n "$FWDIR" ]; then
	echo "::group::firmware"
	# modem.mbn is 62 MiB of carrier configs we have no use for during bring-up.
	mkdir -p "$ROOT/lib/firmware/qcom/sm7150"
	if [ -d "$FWDIR/lib/firmware/qcom/sm7150/courbet" ]; then
		rsync -a --exclude 'modem.mbn' --exclude 'modem_pr' \
			"$FWDIR/lib/firmware/qcom/sm7150/courbet" \
			"$ROOT/lib/firmware/qcom/sm7150/"
	fi
	# The courbet dts asks for qcom/sm7150/xiaomi/courbet/... while the firmware
	# repo ships qcom/sm7150/courbet/... . Provide both paths.
	mkdir -p "$ROOT/lib/firmware/qcom/sm7150/xiaomi"
	ln -sfn ../courbet "$ROOT/lib/firmware/qcom/sm7150/xiaomi/courbet"
	# Anything not under the courbet subdir (wlanmdsp, board files, gpu zap).
	if [ -d "$FWDIR/lib/firmware/qcom" ]; then
		rsync -a --ignore-existing \
			--exclude 'sm7150/courbet/modem.mbn' --exclude 'sm7150/courbet/modem_pr' \
			"$FWDIR/lib/firmware/qcom/" "$ROOT/lib/firmware/qcom/"
	fi
	echo "::endgroup::"
fi

echo "::group::pack"
mkdir -p "$(dirname "$OUT")"
( cd "$ROOT" && find . -print0 | cpio --null -o -H newc --quiet | gzip -9 ) > "$OUT"
ls -la "$OUT"
echo "::endgroup::"