# mainline-courbet

Mainline Linux для **Xiaomi Mi 11 Lite 4G** (`courbet`, M2101K9AG, Qualcomm **SM7150** /
Snapdragon 732G). Сборка целиком в GitHub Actions, локально ничего не нужно.

Ник порта: **@qualixxe096**.

## Что такое mainline и зачем он тут

Стоковое ядро courbet — это **downstream**: CAF-форк Linux **4.14** с вендорными патчами
Xiaomi/Qualcomm, которое живёт только в Android-дереве (`MiCode/Xiaomi_Kernel_OpenSource`,
ветка `courbet-r-oss`, платформа называется `sdmmagpie`, msm-id 365). Оно не обновляется,
не переносится на новые версии и тянет за собой весь Android-стек.

**Mainline** — это ядро с kernel.org, то же самое, что работает на серверах и десктопах:
свежие версии, нормальные драйверы, никакой привязки к Android. Для телефона это даёт
postmarketOS, обычный Linux userspace, регулярные обновления и возможность чинить железо
самому.

Цена: mainline не знает конкретную плату, пока кто-то не напишет device tree и драйверы.
Для SM7150 ситуация такая:

* **Драйверы в апстриме есть** — `gcc-sm7150.c`, `dispcc-sm7150.c`, `camcc-sm7150.c`,
  `videocc-sm7150.c`, `pinctrl-sm7150.c`, `interconnect/qcom/sm7150.c`. Но ни один
  in-tree dts их не биндит: они «сироты», добавлены ради форка.
* **Device tree в апстриме нет** — `sm7150.dtsi` в `torvalds/linux` отсутствует (404).
  Ближайший родственник `sm7125.dtsi` — это 17-строчная обёртка над `sc7180.dtsi`.
* Поэтому база — community-дерево **`sm7150-mainline`** (Danila Tikhonov, David Wronek,
  Jens Reidel). Их `sm7150.dtsi` — 5604 строки, standalone.

## Откуда именно эта сборка

`sm7150-xiaomi-courbet.dts` дожил только до тега **v6.13.4** в `sm7150-mainline/linux`
и был выпилен в v6.13.7+ / v6.18 / v7.2. Форк **`kevinwidjaja21/linux`**, ветка
**`courbet_main`** (6.17.0) — самая свежая ревизия, где есть **и** courbet dts,
**и** драйвер панели `panel-k9a-36-02-0a-mp-dsc.c`. Она и стоит по умолчанию.

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

Панель courbet — **K9A 36 02 0A**, 1080x2400@90Hz, DSI **cmd-mode + DSC**. В базовом
pmOS-конфиге `CONFIG_DRM_PANEL_K9A_36_02_0A` **выключен** — именно поэтому сборки с
tip-ревизии получаются headless. `config/courbet.fragment` его включает.

## Что делает наш репозиторий своего

1. `config/base.config` — вендоренный pmOS-конфиг sm7150 (8736 строк), чтобы сборка
   не зависела от доступности gitlab.
2. `config/courbet.fragment` — наши оверрайды: панель K9A, fbcon как единственный
   видимый debug-канал, pstore/ramoops, USB ACM gadget, UFS, clocks/pinctrl/interconnect,
   SPI-тач, `IKCONFIG_PROC`, `DYNAMIC_DEBUG`.
3. `patches/panel-k9a-dcs-write-seq.patch` — **без него ветка `courbet_main` вообще
   не собирается**. Драйвер панели 54 раза вызывает `mipi_dsi_dcs_write_seq()`,
   а 6.17 этот макрос из `<drm/drm_mipi_dsi.h>` удалил: сборка падает с
   `implicit declaration of function` в `drivers/gpu/drm/panel`. Патч возвращает
   макрос локально в драйвер через `mipi_dsi_dcs_write_buffer()` (он на месте и
   семантика та же, включая early return по ошибке), под `#ifndef` — чтобы тот же
   патч применялся и к старым деревьям, где макрос ещё есть. Именно поэтому в
   tip-конфиге pmOS панель выключена: её не чинили, её обошли.
4. `patches/courbet-usb-peripheral.dtsi` — дописывается к board dts: в common dtsi
   `dr_mode = "otg"` + `usb-role-switch` + `power-role = "source"`, из-за чего порт
   уходит в host и gadget не биндится. Форсируем `peripheral` (тот же приём, что
   upstream использует для curtana).
5. `initramfs/init` — PID 1 без rootfs: монтирует proc/sys/dev/configfs, поднимает
   **USB ACM gadget** и отдаёт интерактивный shell на `/dev/ttyGS0` (на хосте это
   обычный COM-порт, на Windows не нужны драйверы) и на `tty1` (fbcon на панели).
6. `scripts/build-initramfs.sh` — Alpine minirootfs 3.21.9 aarch64 + наш init +
   модули ядра + firmware courbet. Firmware-репо кладёт блобы в
   `qcom/sm7150/courbet/`, а dts просит `qcom/sm7150/xiaomi/courbet/` — делаем оба пути.
   `modem.mbn` (62 MiB) исключён.
7. `scripts/mkbootimg.py` — вендоренный AOSP mkbootimg.

## Два boot.img, потому что конвенции две

Локально проверить нечем, а в исходниках задокументированы **две разные** раскладки,
поэтому CI делает обе. Обе — под `fastboot boot`, то есть **загрузка в RAM, ничего
не прошивается**.

| файл | header | kernel | dtb |
|---|---|---|---|
| `boot.img` | v1 | `Image.gz` | приклеен к концу kernel (конвенция postmarketOS, `deviceinfo_header_version="1"`, `append_dtb="true"`) |
| `boot-stock.img` | v2 | несжатый `Image` | отдельной секцией после ramdisk (как stock Android: `header_size=1660@1644`, `dtb_size@1648`) |

Общие параметры: page 4096, base `0x0`, kernel `0x8000`, ramdisk `0x01000000`,
tags `0x100`, dtb `0x01f00000`. cmdline `console=tty0 loglevel=8 ignore_loglevel`
(ABL дописывает его к `chosen/bootargs`, последний `console=` выигрывает → fbcon).

## Как запустить сборку

```bash
gh workflow run build.yml -R qualixxe/mainline-courbet
gh run watch -R qualixxe/mainline-courbet
```

Inputs: `kernel_repo`, `kernel_ref` (например `sm7150-mainline/linux` + `v6.13.4` как
fallback), `with_firmware`, `cmdline`. Результат — GitHub Release с `boot.img`,
`boot-stock.img`, `initramfs.cpio.gz`, `Image.gz`, dtb, `config`, `MANIFEST.txt`,
`SHA256SUMS.txt`, `build.log`.

## Как проверять на телефоне

Нужен разблокированный загрузчик. **Ничего не прошиваем** — только `fastboot boot`:

```bash
adb reboot bootloader
fastboot boot boot.img          # если не пошло — fastboot boot boot-stock.img
```

Дальше телефон должен появиться как COM-порт (`USB Serial Device`). Открыть его
любым терминалом (PuTTY, `python -m serial.tools.miniterm COMx 115200`) — внутри
shell. Полезное:

```sh
uname -a ; cat /proc/cmdline
dmesg | less            # или /tmp/dmesg.txt
zcat /proc/config.gz
ls /sys/fs/pstore       # логи прошлого неудачного boot
ls /sys/class/udc /sys/class/drm /sys/block
reboot -f
```

Если экран загорелся и пошли Penguins/лог — kernel дошёл до DRM. Если чёрный экран,
но COM-порт есть — жив kernel, не жива панель. Если нет ничего — **warm reboot** в
recovery и читать `/sys/fs/pstore/console-ramoops-0`: ramoops переживает перезагрузку.

### Подводные камни, которые надо знать заранее

* **DTBO.** `fastboot boot` **не обходит** обработку DTBO: stock dtbo не должен
  применяться к mainline DTB. По заметкам порта его нужно стирать
  (`fastboot erase dtbo`) — это **запись в телефон**, делать только осознанно.
* **AVB.** У courbet `android,vbmeta` с `parts="vbmeta,boot,system,vendor,dtbo,recovery"`.
  Может понадобиться vbmeta с отключённой верификацией — тоже запись, тоже отдельно.
* Тач у courbet — **SPI** (`xiaomi,spits`, `qupv3_se4_spi`, irq tlmm 9, reset tlmm 8),
  а не i2c goodix/fts: те узлы в downstream — мёртвый boilerplate. Драйвера под
  `xiaomi,spits` в mainline нет, так что тач, скорее всего, не заработает.

## Ожидаемый статус железа

По wiki postmarketos для courbet на этом форке:

* **работает**: display, GPU, WiFi (WCN3990 SNOC / ath10k), battery, modem, NFC, OTG
* **не работает**: touch, audio, camera, GPS, sensors

Это ориентир, а не гарантия нашей сборки: **зелёный CI означает только то, что ядро
собралось и упаковано. Загрузку на телефоне ещё никто не подтверждал.**

## Ссылки

* https://github.com/sm7150-mainline/linux — основное community-дерево SM7150
* https://github.com/kevinwidjaja21/linux/tree/courbet_main — 6.17 с courbet dts + панель
* https://github.com/sm7150-mainline/firmware-xiaomi-courbet — блобы
* https://gitlab.postmarketos.org/kevinwidjaja21/pmaports — ветка `courbet_stable`
* https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/courbet-r-oss — downstream 4.14
* https://wiki.postmarketos.org/wiki/Xiaomi_Mi_11_Lite_4G_(xiaomi-courbet)