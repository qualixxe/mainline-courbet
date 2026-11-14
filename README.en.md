# mainline-courbet

[🇷🇺 Русский](README.md) · **🇬🇧 English**

Mainline Linux for the **Xiaomi Mi 11 Lite 4G** (`courbet`, M2101K9AG, Qualcomm **SM7150** / Snapdragon 732G). This repository contains kernel source and configuration; build it locally only.

Author: **@qualixxe096**.

## What mainline is and why it is used here

The stock courbet kernel is **downstream**: a CAF fork of Linux **4.14** with Xiaomi/Qualcomm vendor patches. It lives in the Android tree (`MiCode/Xiaomi_Kernel_OpenSource`, branch `courbet-r-oss`, platform `sdmmagpie`, msm-id 365), is not updated or ported to newer versions, and depends on the Android stack.

**Mainline** is the kernel from kernel.org—the same kernel family used on servers and desktops. It brings newer versions, standard drivers, no Android dependency, and makes postmarketOS and a regular Linux userspace possible. The trade-off is that mainline needs device-tree support and drivers for each specific board.

For SM7150:

* **Some drivers are upstream**: `gcc-sm7150.c`, `dispcc-sm7150.c`, `camcc-sm7150.c`, `videocc-sm7150.c`, `pinctrl-sm7150.c`, and `interconnect/qcom/sm7150.c`. No in-tree DTS binds them; they are effectively orphans, added for the fork.
* **The device tree is not upstream**: `sm7150.dtsi` is absent from `torvalds/linux`. The closest relative, `sm7125.dtsi`, is a 17-line wrapper around `sc7180.dtsi`.
* The base is therefore the community **`sm7150-mainline`** tree (Danila Tikhonov, David Wronek, Jens Reidel), whose standalone `sm7150.dtsi` is 5,604 lines.

## Kernel source used for this build

`sm7150-xiaomi-courbet.dts` was present in `sm7150-mainline/linux` through **v6.13.4**, then removed in v6.13.7+ / v6.18 / v7.2. The **`courbet_main`** branch of **`kevinwidjaja21/linux`** (6.17.0) is the newest revision found with both the courbet DTS and the `panel-k9a-36-02-0a-mp-dsc.c` panel driver. It is the default source.

`sm7150-xiaomi-common.dtsi` already provides most of what is needed:

| Node | Purpose |
|---|---|
| `framebuffer@9c000000` | 1080x2400 a8r8g8b8 simple framebuffer, available before DRM |
| `ramoops@9d800000` | 4 MiB pstore (512K record, 2M pmsg, 1M console); logs survive reboot |
| `&ufs_mem_hc` / `&ufs_mem_phy` | UFS at `1d84000` + QMP PHY at `1d87000`, the main storage |
| `&sdhc_2` | microSD (`8804000`), cd-gpio tlmm 69 |
| `&mdss` / `&mdss_dsi0` / `&dispcc` | DPU + DSI 10nm PHY, all enabled |
| `&gpu` | Adreno 618, zap shader `a615_zap.mbn` |
| `chosen` | `stdout-path = "serial0:115200n8"`, bootargs `earlycon console=ttyMSM0,115200` |

The courbet panel is **K9A 36 02 0A**, 1080x2400@90Hz, DSI **command mode + DSC**. The base pmOS config disables `CONFIG_DRM_PANEL_K9A_36_02_0A`, which is why builds from the tip revision are headless. `config/courbet.fragment` enables it.

## What this repository adds

1. `config/base.config` — vendored pmOS SM7150 config (8,736 lines), so builds do not depend on GitLab availability.
2. `config/courbet.fragment` — local overrides: K9A panel, fbcon as the only visible debug channel, pstore/ramoops, USB ACM gadget, UFS, clocks/pinctrl/interconnect, SPI touchscreen, `IKCONFIG_PROC`, and `DYNAMIC_DEBUG`.
3. `patches/panel-k9a-dcs-write-seq.patch` — required to build `courbet_main`. The panel driver calls `mipi_dsi_dcs_write_seq()` 54 times, but Linux 6.17 removed this macro from `<drm/drm_mipi_dsi.h>`, causing an implicit-declaration build error. The patch locally restores it in the driver using `mipi_dsi_dcs_write_buffer()` (which remains available), preserving error handling and using `#ifndef` so it also applies to older trees. The pmOS tip config disables the panel rather than fixing it.
4. `patches/courbet-usb-peripheral.dtsi` — appended to the board DTS. The common DTS sets `dr_mode = "otg"`, `usb-role-switch`, and `power-role = "source"`, which puts the port in host mode and prevents the gadget from binding. This forces `peripheral`, as upstream does for curtana.
5. `initramfs/init` — PID 1 without a root filesystem. It mounts proc/sys/dev/configfs, starts a **USB ACM gadget**, and provides an interactive shell on `/dev/ttyGS0` (a regular COM port on the host; no Windows driver needed) and `tty1` (fbcon on the panel).
6. `scripts/build-initramfs.sh` — Alpine minirootfs 3.21.9 aarch64 + our init + `16x32` font + kernel modules + courbet firmware + Adreno 618 microcode (`a630_sqe.fw`, `a630_gmu.bin`). Firmware is installed under `qcom/sm7150/courbet/`, while the DTS requests `qcom/sm7150/xiaomi/courbet/`, so both paths are created. `modem.mbn` (62 MiB) and DSP/venus/wlan blobs (~27 MiB) are excluded so the ramdisk fits below the DTB address `0x01f00000`.
7. **Display-stack patches (DPU1 + DSI + DSC + K9A)** make the display produce a clean image without FIFO errors or stripes:
   * `patches/panel-k9a-dsc-topology.patch` — DSC slice geometry `1080×12`, `slice_count = 1`, `8 bpp` (instead of the incorrect `10 bpp`), matching the panel's factory register `0x91`.
   * `patches/dpu-dsc-single-slice.patch` — topology `<1 1 1>` (one LM, one DSC, one INTF) instead of mainline's forced `num_dsc = 2`.
   * `patches/panel-k9a-dsi-format-24bit.patch` and `patches/dsi-pclk-bus-width.patch` — align the compressed DPU→DSI bus width (`3 bytes/pclk` = 24 bits, not 30-bit `RGB101010`), setting `pclk = 85.24 MHz` and `byte_clk = 63.93 MHz` and eliminating the `FIFO_STATUS = 0x88881310` storm.
   * `patches/dsi-dsc-10bpc-8bpp-qp0.patch` — sets `rc_range_params[0].range_max_qp = 8` (instead of the VESA DSC 1.1 pre-SCR table's `7`) for `10 bpc @ 8 bpp`, matching the stock Qualcomm/Xiaomi driver and factory courbet PPS; removes horizontal and side DSC stripes.
   * `patches/dsi-fifo-status-once.patch` — logs raw `DSI_FIFO_STATUS` once at startup.
8. `scripts/mkbootimg.py` — vendored AOSP mkbootimg.
9. `scripts/local-boot-edit.py` — locally unpacks and repacks `boot.img` in about one second on Windows/Linux, without rebuilding the kernel in GitHub Actions.

## Boot image format: read from the phone itself

The layout was not guessed: the courbet `boot` partition was dumped and its header inspected. It uses:

| Field | Value |
|---|---|
| `header_version` | **2** (`header_size=1660@1644`, `dtb_size@1648`, `dtb_addr@1652`) |
| Kernel | **gzip** `Image.gz`, not raw `Image` |
| DTB | A separate section, not appended to the kernel |
| Addresses | kernel `0x8000`, ramdisk `0x01000000`, tags `0x100`, DTB `0x01f00000` |
| Page / base | 4096 / `0x0` |
| `os_version` | `0x1a00017a` = `--os_version 13.0.0 --os_patch_level 2023-10` |

Two conclusions were verified on the phone:

* **ABL does not accept a raw `Image`**: it reports `Failed to load/authenticate boot image: Load Error`. Use gzip.
* **The ramdisk must fit below `0x01f00000`**, or it overlaps the DTB. The full initramfs with DSP blobs is 25.3 MiB and does not fit. `build-initramfs.sh` excludes `adsp/cdsp/venus/wlanmdsp` (~27 MiB unpacked), which are not needed for the shell. The result is **11.6 MiB**, leaving about 3.4 MiB before the DTB.

CI produces two images for `fastboot boot`—**they are loaded into RAM, not flashed**. The command line is `console=tty0 loglevel=8 ignore_loglevel` (ABL appends it to `chosen/bootargs`; the last `console=` wins, selecting fbcon).

`scripts/bootinfo.py` prints the `[addr, addr+size)` map for each image and **fails CI** if sections overlap. Current `boot.img` map:

```
kernel   0x00008000 .. 0x00dba7b0  (14362544)
ramdisk  0x01000000 .. 0x01b9692f  (12151087)
dtb      0x01f00000 .. 0x01f15bcc  (89036)
```

Sizes: initramfs 11.6 MiB, `boot.img` 25.4 MiB.

## Boot on the phone

Nothing is flashed; this is a temporary boot into RAM only:

```bash
adb reboot bootloader
fastboot boot boot.img
```

Verified `boot.img`:
https://github.com/qualixxe/mainline-courbet/releases/download/courbet-screen-fixed/boot.img

### Ready-to-use display test image

The image has been confirmed with `fastboot boot` on a connected `courbet`:
https://github.com/qualixxe/mainline-courbet/releases/download/courbet-screen-fixed/boot.img

This is a locally patched binary image (display-stack patches are also applied in this repository's sources). Use **only** `fastboot boot`; do not flash partitions. The alternative `boot-pmos.img` was repacked for testing but has not been verified on the phone.

## Edit `boot.img` locally, without GitHub Actions

To change the initramfs (`init`, fonts, modules, blobs), `cmdline`, `device.dtb`, or test binary kernel patches on a PC in about one second instead of waiting 20 minutes for CI:

```bash
# Unpack a ready boot.img (extracts Image, device.dtb, boot-meta.json and initramfs/)
python scripts/local-boot-edit.py unpack boot.img work/

# Edit files in work/initramfs/, cmdline in work/boot-meta.json,
# DTB in work/device.dtb or kernel in work/Image, then repack:
python scripts/local-boot-edit.py repack work/ boot-test.img

# Test in RAM; no partition is flashed
fastboot boot boot-test.img
```

## postmarketOS integration (`pmos-courbet`)

The [qualixxe/pmos-courbet](https://github.com/qualixxe/pmos-courbet) repository contains the courbet postmarketOS device port, including `device/courbet.deviceinfo` and `mkbootimg.py`.

To use a 6.17 kernel with the display fixes from this repository, unpack a working image and repack it with the postmarketOS files/initramfs. Example:

```bash
# 1. Unpack any working boot.img (for example, from the courbet-screen-fixed release)
python scripts/local-boot-edit.py unpack boot.img work/

# 2. Copy files from pmos-courbet (deviceinfo, init scripts, etc.) into work/initramfs/
#    Replace init if desired.

# 3. Build a hybrid image:
python scripts/local-boot-edit.py repack work/ boot-pmos.img

# Or use the ready-made script:
./scripts/build-pmos-boot.sh work/ boot-pmos.img

# 4. Boot it:
fastboot boot boot-pmos.img
```

A locally built `boot-pmos.img` (kernel 6.17 + display patches + Alpine initramfs) is available at `out/boot-pmos.img`. It can be added to a release if desired.

## Testing on the phone

The bootloader must be unlocked. **Do not flash anything**; use `fastboot boot` only:

```bash
adb reboot bootloader
fastboot boot boot.img          # if that fails, try fastboot boot boot-pmos.img
```

The phone should appear as a COM port (`USB Serial Device`). Open it with a terminal (PuTTY, or `python -m serial.tools.miniterm COMx 115200`) to get a shell. Useful commands:

```sh
uname -a ; cat /proc/cmdline
dmesg | less            # or /tmp/dmesg.txt
zcat /proc/config.gz
ls /sys/fs/pstore       # logs from the previous failed boot
ls /sys/class/udc /sys/class/drm /sys/block
reboot -f
```

If the display lights up and Penguins/log output appears, the kernel reached DRM. If the screen is black but the COM port exists, the kernel is alive but the panel is not. If nothing appears, warm-reboot into recovery and read `/sys/fs/pstore/console-ramoops-0`: ramoops survives reboot.

### Important caveats

* **DTBO — confirmed by inspecting the dump.** `fastboot boot` does **not** bypass DTBO processing. The stock courbet `dtbo` contains one entry with all IDs set to zero (`id=0 rev=0 custom=[0,0,0]`), i.e. a wildcard, so ABL applies it to any DTB. Its root declares `qcom,msm-id = <365 0>` and `qcom,board-id = <45 0>`, matching our DTB. The overlay contains 1,075 nodes / 6,153 properties from the downstream `qcom,sdmmagpie` tree; its `__fixups__` require base-tree symbols such as `CPU0..CPU7`, `soc`, `tlmm`, `mdss_mdp`, `mdss_dsi0`, `ufsphy_mem`, `ufshc_mem`, `sdhc_1/2`, and `pm6150_l13`. Our mainline DTB has no `__symbols__` node and uses different names, so ABL cannot resolve the fixups. The overlay changes CPU/soc/tlmm, which can kill the kernel before console output. Erasing it (`fastboot erase dtbo`) is a remedy, but **it writes to the phone**: do it only deliberately and with a partition backup.
* **AVB.** courbet's `android,vbmeta` has `parts="vbmeta,boot,system,vendor,dtbo,recovery"`. A vbmeta image with verification disabled may also be needed; this is another write and must be considered separately.
* The courbet touchscreen is **SPI** (`xiaomi,spits`, `qupv3_se4_spi`, irq tlmm 9, reset tlmm 8), not I2C Goodix/FTS; those downstream nodes are dead boilerplate. Mainline has no `xiaomi,spits` driver, so touch is unlikely to work.

## Expected hardware status

According to the postmarketOS courbet wiki for this fork:

* **Working:** display, GPU, Wi-Fi (WCN3990 SNOC / ath10k), battery, modem, NFC, OTG
* **Not working:** touch, audio, camera, GPS, sensors

This is a reference, not a guarantee for this build.

## Actual status as of 2026-11-14

**Mainline boots on courbet and provides a shell.** This was confirmed on the device, not inferred from logs: the phone brings up a USB ACM gadget (`1d6b:0104`, serial `0123456789`), visible as a COM port on the host, with an interactive shell. Uptime exceeded 90 minutes; pstore was clean. All tests used `fastboot boot` (RAM); no partition was flashed.

Working:

* **Display (AMOLED K9A `36_02_0a`, 1080×2400, DSC 10bpc/8bpp, command mode):** clean image without artifacts or stripes, **0 DSI FIFO errors**, fbcon console with `16×32` font, brightness control at `/sys/class/backlight/ae94000.dsi.0/brightness` (`0..2047`).
* **Adreno 618 GPU:** firmware `qcom/a630_sqe.fw` and `qcom/a630_gmu.bin` load; DRM/MSM (`ae01000.display-controller`) initializes normally.
* 8 CPUs, 5,475 MiB RAM, and all UFS partitions are visible.
* USB gadget + ACM shell (`/dev/ttyGS0`).
* ramoops/pstore, debugfs, fbdev emulation (`fb0`, 32 bpp, stride 4352).

Not working / not yet included in the initramfs:

* **Wi-Fi.** `firmware-xiaomi-courbet` contains only `wlanmdsp.mbn`; `ath10k_snoc` also needs `ath10k/WCN3990/hw1.0/firmware-5.bin` and `board-2.bin` from linux-firmware. They are omitted from the initramfs to stay below the `< 15 MiB` limit before DTB address `0x01f00000`.
* **Touch, audio, camera, GPS, sensors:** mainline drivers are missing (including SPI `xiaomi,spits`).

### How the display was fixed (three independent mainline bugs)

1. **DSC topology `1:1:1` and slice `1080×12 @ 8 bpp`.** The factory `dsi-panel-k9a-36-02-0a-mp-dsc-cmd.dtsi` and DTBO dump specify **one** DSC slice, 1080 pixels wide at **8 bpp** (`qcom,display-topology = <1 1 1>`); the panel's vendor register `0x91` is hard-coded for one 1080-pixel slice. Mainline reserved two DSC blocks and split the width in half, while the panel driver used `10 bpp`. Fixed by `panel-k9a-dsc-topology.patch` and `dpu-dsc-single-slice.patch`.
2. **`FIFO_STATUS = 0x88881310` storm (30-bit vs 24-bit DPU→DSI bus mismatch).** After switching to `1:1:1`, DSI generated about 18,500 interrupts/s: `CMD_MDP_FIFO_OVERFLOW` and `DLN0..DLN3 HS FIFO UNDERFLOW`. With DSC enabled, DPU sends compressed data to DSI at **3 bytes per `pclk`** (24 bits), regardless of `bits_per_component = 10`. `MIPI_DSI_FMT_RGB101010` (30 bits) and division by `bits_per_component * 3` in `dsi_adjust_pclk_for_compression()` reduced pixel clock by 25% (`69.58 MHz`) and raised `byte_clk` above the DPU feed rate. Changing the bus format to 24 bits and calculating `pclk` from the actual bus width set `pclk = 85.24 MHz`, `byte_clk = 63.93 MHz`; FIFO errors dropped to **zero**.
3. **Horizontal/side stripes around text (`range_max_qp[0]: 7 → 8`).** The VESA DSC 1.1 pre-SCR table in `drm_dsc_helper.c` sets `rc_range_params[0].range_max_qp = 7` for `10 bpc @ 8 bpp`. Qualcomm/Xiaomi's downstream `dsi_panel.c` and the K9A factory PPS override range zero to **`8`** (register `dsc_0 + 0xb0 = 0x8`). With `7`, flat areas such as the console background next to glyphs showed DSC overflow/quantization stripes. `dsi-dsc-10bpc-8bpp-qp0.patch` synchronizes the panel PPS and DPU1 `DSC_RANGE_MAX_QP_0` at `8`; the stripes disappeared.

### What fixed booting

The stock DTBO (see the caveat above) was the cause. After `fastboot erase dtbo`, the kernel reached console and started the gadget. A partition backup is stored locally (33,554,432 bytes, SHA-256 `82d9143b…`). **While DTBO is erased, the stock Android firmware may not boot correctly.** Restoring it writes to the phone and is handled separately, with explicit consent.

Hypotheses ruled out during debugging: overlapping image sections (map is clean), “16K pages” (`flags=0xa` on stock too, `ARM64_4K_PAGES=y`), anti-rollback via `os_version`, video/command-mode mismatch (MSM host checks only `MIPI_DSI_MODE_VIDEO`), missing PMIC regulators, console blanking (`consoleblank=0`), the `dcs_write_seq` patch, and panel initialization failure.

**Re-tested on a connected Xiaomi Mi 11 Lite 4G:** the image booted via `fastboot boot`, without flashing a partition. The panel displayed text on a blue background; after overriding `range_max_qp[0] = 8`, the user confirmed the stripes disappeared. The serial shell confirmed `pclk = 85.24 MHz`, `byte_clk = 63.93 MHz`, backlight enabled, and no previous FIFO storm.

## References

* https://github.com/sm7150-mainline/linux — main community SM7150 tree
* https://github.com/kevinwidjaja21/linux/tree/courbet_main — 6.17 with courbet DTS + panel
* https://github.com/sm7150-mainline/firmware-xiaomi-courbet — firmware blobs
* https://gitlab.postmarketos.org/kevinwidjaja21/pmaports — `courbet_stable` branch
* https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/courbet-r-oss — downstream 4.14
* https://github.com/Aciss21/kernel_xiaomi_sm6150/tree/aosp — downstream courbet 4.14.357-openela; source of the factory panel configuration: `arch/arm64/boot/dts/qcom/xiaomi/courbet/dsi-panel-k9a-36-02-0a-mp-dsc-cmd.dtsi` and `drivers/gpu/drm/msm/dsi-staging/` (`aosp`/`oem` branches, not `16`)
* https://wiki.postmarketos.org/wiki/Xiaomi_Mi_11_Lite_4G_(xiaomi-courbet)
