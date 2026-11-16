<p align="center">
  <a href="#ru"><strong>Русский</strong></a> ·
  <a href="#en"><strong>English</strong></a>
</p>

<details id="ru" open>
<summary><strong>Русский</strong></summary>

# mainline-courbet

Mainline Linux для **Xiaomi Mi 11 Lite 4G** (`courbet`, M2101K9AG, Qualcomm **SM7150** / Snapdragon 732G). Код ядра и конфиги в этом репозитории — собирать только локально.

Автор: **@qualixxe096**.

## Что такое mainline и зачем он тут

Стоковое ядро courbet — это **downstream**: CAF-форк Linux **4.14** с вендорными патчами Xiaomi/Qualcomm, которое живёт только в Android-дереве (`MiCode/Xiaomi_Kernel_OpenSource`, ветка `courbet-r-oss`, платформа называется `sdmmagpie`, msm-id 365). Он не обновляется, не переносится на новые версии и тянет за собой весь Android-стек.

**Mainline** — это ядро с kernel.org, то же самое, что работает на серверах и десктопах: свежие версии, нормальные драйверы, никакой привязки к Android. Для телефона это даёт postmarketOS, обычный Linux userspace, регулярные обновления и возможность чинить железо самому.

Цена: mainline не знает конкретную плату, пока кто-то не напишет device tree и драйверы. Для SM7150 ситуация такая:

* **Драйверы в апстриме есть** — `gcc-sm7150.c`, `dispcc-sm7150.c`, `camcc-sm7150.c`, `videocc-sm7150.c`, `pinctrl-sm7150.c`, `interconnect/qcom/sm7150.c`. Но ни один in-tree dts их не биндит: они «сироты», добавлены ради форка.
* **Device tree в апстриме нет** — `sm7150.dtsi` в `torvalds/linux` отсутствует (404). Ближайший родственник `sm7125.dtsi` — это 17-строчная обёртка над `sc7180.dtsi`.
* Поэтому база — community-дерево **`sm7150-mainline`** (Danila Tikhonov, David Wronek, Jens Reidel). Их `sm7150.dtsi` — 5604 строки, standalone.

## Откуда именно эта сборка

`sm7150-xiaomi-courbet.dts` дожил только до тега **v6.13.4** в `sm7150-mainline/linux` и был выпилен в v6.13.7+ / v6.18 / v7.2. Форк **`kevinwidjaja21/linux`**, ветка **`courbet_main`** (6.17.0) — самая свежая ревизия, где есть **и** courbet dts, **и** драйвер панели `panel-k9a-36-02-0a-mp-dsc.c`. Она и стоит по умолчанию.

В `sm7150-xiaomi-common.dtsi` уже есть почти всё нужное:

| узел | что это |
|---|---|
| `framebuffer@9c000000` | simple-framebuffer 1080x2400 a8r8g8b8 — ранний экран ещё до DRM |
| `ramoops@9d800000` | 4 MiB pstore: record 512K, pmsg 2M, console 1M — логи переживают ребут |
| `&ufs_mem_hc` / `&ufs_mem_phy` | UFS `1d84000` + QMP phy `1d87000` — основной накопитель |
| `&sdhc_2` | microSD (`8804000`), cd-gpio tlmm 69 |
| `&mdss` / `&mdss_dsi0` / `&dispcc` | DPU + DSI 10nm phy, всё `status = "okay"` |
| `&gpu` | Adreno 618, zap-shader `a615_zap.mbn` |
| `chosen` | `stdout-path = "serial0:115200n8"`, bootargs `earlycon console=ttyMSM0,115200` |

Панель courbet — **K9A 36 02 0A**, 1080x2400@90Hz, DSI **cmd-mode + DSC**. В базовом pmOS-конфиге `CONFIG_DRM_PANEL_K9A_36_02_0A` **выключен** — именно поэтому сборки с tip-ревизии получаются headless. `config/courbet.fragment` его включает.

## Что делает наш репозиторий своего

1. `config/base.config` — вендоренный pmOS-конфиг sm7150 (8736 строк), чтобы сборка не зависела от доступности gitlab.
2. `config/courbet.fragment` — наши оверрайды: панель K9A, fbcon как единственный видимый debug-канал, pstore/ramoops, USB ACM gadget, UFS, clocks/pinctrl/interconnect, SPI-тач, `IKCONFIG_PROC`, `DYNAMIC_DEBUG`.
3. `patches/panel-k9a-dcs-write-seq.patch` — **без него ветка `courbet_main` вообще не собирается**. Драйвер панели 54 раза вызывает `mipi_dsi_dcs_write_seq()`, а 6.17 этот макрос из `<drm/drm_mipi_dsi.h>` удалил: сборка падает с `implicit declaration of function` в `drivers/gpu/drm/panel`.
4. `patches/courbet-usb-peripheral.dtsi` — дописывается к board dts: в common dtsi `dr_mode = "otg"` + `usb-role-switch` + `power-role = "source"`, из-за чего порт уходит в host и gadget не биндится. Форсируем `peripheral`.
5. `initramfs/init` — PID 1 без rootfs: монтирует proc/sys/dev/configfs, поднимает **USB ACM gadget** и отдаёт интерактивный shell на `/dev/ttyGS0` и `tty1`.
6. `scripts/build-initramfs.sh` — Alpine minirootfs 3.21.9 aarch64 + наш init + шрифт `16x32` + модули ядра + firmware courbet + микрокод Adreno 618.
7. **Патчи дисплейного стека (`DPU1 + DSI + DSC + K9A`)** — доводят экран до чистой картинки без ошибок FIFO и полос.
8. `scripts/mkbootimg.py` — вендоренный AOSP mkbootimg.
9. `scripts/local-boot-edit.py` — локальная распаковка и пересборка `boot.img` за ~1 секунду.

## Упаковка: конвенция снята с самого телефона

Раскладка не угадана — **снят дамп собственного раздела `boot` courbet и прочитан его заголовок**. Он оказался таким:

| поле | значение |
|---|---|
| `header_version` | **2** |
| kernel | **gzip** `Image.gz` |
| dtb | отдельной секцией |
| адреса | kernel `0x8000`, ramdisk `0x01000000`, tags `0x100`, dtb `0x01f00000` |
| page / base | 4096 / `0x0` |
| `os_version` | `0x1a00017a` |

## Как запустить на телефоне

Ничего не прошиваем — только временная загрузка в RAM:

```bash
adb reboot bootloader
fastboot boot boot.img
```

Готовый проверенный `boot.img`:
https://github.com/qualixxe/mainline-courbet/releases/download/courbet-screen-fixed/boot.img

## Локальная правка `boot.img` без GitHub Actions

```bash
python scripts/local-boot-edit.py unpack boot.img work/
python scripts/local-boot-edit.py repack work/ boot-test.img
fastboot boot boot-test.img
```

## ??????? ??????

**Mainline ??????????? ?? courbet ? ??????? ?? shell.** ????? ? ??????? ?????????. ??? ???? bring-up ? RAM, ?? ????????????? ????????? ??.

Boot-?????? ???????????? ????????:
- [Fixed display boot](https://github.com/qualixxe/mainline-courbet/releases/tag/courbet-fixed-boot) ? ??????????? ??????? ? ???????????? ??????.
- [pmOS boot](https://github.com/qualixxe/mainline-courbet/releases/tag/courbet-pmos-boot) ? Alpine-based initramfs.
- [Arch rootfs experiment](https://github.com/qualixxe/mainline-courbet/releases/tag/courbet-arch-experimental) ? ????????????????? ????????. ? ?????? ???? Arch release metadata, ?? ???????????? Arch userspace, `pacman` ? ???????? ????? ???; shell ?? ?????????? ????????? Alpine. ??? ?? ??????? Arch-???????.

??? ???????? ?????????? ?????? ????? `fastboot boot`; ?? ?????????? ???????. ??? Arch desktop ??? ????? rootfs ?? ????????? ???????? ???????, ???????? ? ??? ? ??????????? DRM/Wayland-?????. `userdata` ?? ???????? ??? ????????? ?????.

## Ссылки

* https://github.com/sm7150-mainline/linux
* https://github.com/kevinwidjaja21/linux/tree/courbet_main
* https://github.com/sm7150-mainline/firmware-xiaomi-courbet
* https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/courbet-r-oss
* https://wiki.postmarketos.org/wiki/Xiaomi_Mi_11_Lite_4G_(xiaomi-courbet)

</details>

<details id="en" open>
<summary><strong>English</strong></summary>

# mainline-courbet

Mainline Linux for the **Xiaomi Mi 11 Lite 4G** (`courbet`, M2101K9AG, Qualcomm **SM7150** / Snapdragon 732G). This repository contains the kernel source and build configuration; build it locally only.

Author: **@qualixxe096**.

## What mainline is and why it is here

The stock `courbet` kernel is a **downstream** kernel: a CAF fork of Linux **4.14** with Xiaomi/Qualcomm vendor patches. It is tied to the Android tree (`MiCode/Xiaomi_Kernel_OpenSource`, branch `courbet-r-oss`, platform `sdmmagpie`, msm-id 365). It is not updated, not ported to newer versions, and pulls in the entire Android stack.

**Mainline** is the kernel from kernel.org: the same kernel used on servers and desktops. It brings newer versions, standard drivers, no Android dependency, and enables postmarketOS and a normal Linux userspace on phones.

The downside is that mainline does not know your specific board until someone writes the device tree and drivers. For SM7150:

* **Drivers are upstream**: `gcc-sm7150.c`, `dispcc-sm7150.c`, `camcc-sm7150.c`, `videocc-sm7150.c`, `pinctrl-sm7150.c`, and `interconnect/qcom/sm7150.c`.
* **The device tree is not upstream**: `sm7150.dtsi` is missing from `torvalds/linux`.
* Therefore the baseline is the community **`sm7150-mainline`** tree, whose standalone `sm7150.dtsi` is 5,604 lines long.

## Where this build comes from

`sm7150-xiaomi-courbet.dts` survives only until **v6.13.4** in `sm7150-mainline/linux`; it was removed in v6.13.7+ / v6.18 / v7.2. The **`kevinwidjaja21/linux`** fork, branch **`courbet_main`** (6.17.0), is the newest revision found with both the courbet DTS and the `panel-k9a-36-02-0a-mp-dsc.c` panel driver. That is the default source.

The repository adds several important pieces:

1. `config/base.config` — vendored pmOS SM7150 config to avoid depending on GitLab availability.
2. `config/courbet.fragment` — local overrides for K9A panel, fbcon, pstore/ramoops, USB ACM gadget, UFS, clocks, pinctrl, SPI touch, `IKCONFIG_PROC`, and `DYNAMIC_DEBUG`.
3. `patches/panel-k9a-dcs-write-seq.patch` — required because the panel driver uses `mipi_dsi_dcs_write_seq()` and Linux 6.17 removed that macro.
4. `patches/courbet-usb-peripheral.dtsi` — ensures USB is forced to peripheral mode instead of host mode.
5. `initramfs/init` — PID 1 without rootfs, starting the USB ACM gadget and shell.
6. `scripts/build-initramfs.sh` — builds a minimal Alpine initramfs with kernel modules and firmware.
7. **Display patches** — fix major DSC/DPU/DSI issues so the panel renders properly without FIFO errors or stripes.
8. `scripts/local-boot-edit.py` — unpack/repack `boot.img` locally in seconds.

## Boot on the phone

No partition is flashed; only a temporary RAM boot is used:

```bash
adb reboot bootloader
fastboot boot boot.img
```

Working release image:
https://github.com/qualixxe/mainline-courbet/releases/download/courbet-screen-fixed/boot.img

## Local editing without GitHub Actions

```bash
python scripts/local-boot-edit.py unpack boot.img work/
python scripts/local-boot-edit.py repack work/ boot-test.img
fastboot boot boot-test.img
```

## Current status

**Mainline boots on `courbet` and reaches a shell.** The display and console have been tested. This is still a RAM bring-up, not an installed mobile OS.

Boot images are published separately:
- [Fixed display boot](https://github.com/qualixxe/mainline-courbet/releases/tag/courbet-fixed-boot) ? screen-fix variant tested on the phone.
- [pmOS boot](https://github.com/qualixxe/mainline-courbet/releases/tag/courbet-pmos-boot) ? Alpine-based initramfs.
- [Arch rootfs experiment](https://github.com/qualixxe/mainline-courbet/releases/tag/courbet-arch-experimental) ? packaging experiment only. It has Arch release metadata, but no complete Arch userspace, `pacman`, or desktop; the device shell reported Alpine. It is not a usable Arch installation.

Use `fastboot boot` only; do not flash partitions. An Arch desktop still needs a rootfs on a separate filesystem, a working boot path, and a tested DRM/Wayland session. Do not modify `userdata` without a backup.

## Notes

The repository includes a complete Russian version and a separate English translation in [`README.en.md`](README.en.md). This page keeps both language views in one place with a language switch at the top.

</details>

<p align="center">
  <sub>Русский / English switch is done with GitHub-compatible collapsible sections.</sub>
</p>
