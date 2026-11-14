# mainline-courbet

Mainline Linux для **Xiaomi Mi 11 Lite 4G** (`courbet`, M2101K9AG, Qualcomm **SM7150** /
Snapdragon 732G). Код ядра и конфиги в этом репозитории — собирать только локально.

Автор: **@qualixxe096**.

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
   шрифт `16x32` + модули ядра + firmware courbet + микрокод Adreno 618 (`a630_sqe.fw`,
   `a630_gmu.bin`). Firmware-репо кладёт блобы в `qcom/sm7150/courbet/`, а dts просит
   `qcom/sm7150/xiaomi/courbet/` — делаем оба пути. Исключены `modem.mbn` (62 MiB) и
   DSP/venus/wlan-блобы (~27 MiB): ramdisk должен влезть под адрес dtb `0x01f00000`.
7. **Патчи дисплейного стека (`DPU1 + DSI + DSC + K9A`)** — доводят экран до полностью
   чистой картинки без ошибок FIFO и полос:
   * `patches/panel-k9a-dsc-topology.patch` — геометрия DSC слайса `1080×12`, `slice_count = 1`,
     `8 bpp` (вместо ошибочных `10 bpp`), строго под заводской регистр `0x91` панели;
   * `patches/dpu-dsc-single-slice.patch` — топология `<1 1 1>` (один LM, один DSC, один INTF)
     вместо принудительного `num_dsc = 2` в mainline;
   * `patches/panel-k9a-dsi-format-24bit.patch` и `patches/dsi-pclk-bus-width.patch` — согласование
     ширины шины сжатого потока DPU→DSI (`3 байта/pclk` = 24 бит вместо 30-битного `RGB101010`),
     переводящее частоты в `pclk = 85.24 МГц`, `byte_clk = 63.93 МГц` и полностью убирающее
     шторм `FIFO_STATUS = 0x88881310`;
   * `patches/dsi-dsc-10bpc-8bpp-qp0.patch` — оверрайд `rc_range_params[0].range_max_qp = 8`
     (вместо `7` из таблицы VESA DSC 1.1 pre-SCR) для `10 bpc @ 8 bpp`, как в стоковом драйвере
     Qualcomm/Xiaomi и заводском PPS courbet — убирает горизонтальные и боковые DSC-полосы;
   * `patches/dsi-fifo-status-once.patch` — однократный лог сырого `DSI_FIFO_STATUS` при старте.
8. `scripts/mkbootimg.py` — вендоренный AOSP mkbootimg.
9. `scripts/local-boot-edit.py` — локальная распаковка и пересборка `boot.img` за ~1 секунду
   на Windows/Linux без пересборки ядра в GitHub Actions.

## Упаковка: конвенция снята с самого телефона

Раскладка не угадана — **снят дамп собственного раздела `boot` courbet и прочитан
его заголовок**. Он оказался таким:

| поле | значение |
|---|---|
| `header_version` | **2** (`header_size=1660@1644`, `dtb_size@1648`, `dtb_addr@1652`) |
| kernel | **gzip** `Image.gz`, не сырой `Image` |
| dtb | **отдельной секцией**, не приклеен к kernel |
| адреса | kernel `0x8000`, ramdisk `0x01000000`, tags `0x100`, dtb `0x01f00000` |
| page / base | 4096 / `0x0` |
| `os_version` | `0x1a00017a` = `--os_version 13.0.0 --os_patch_level 2023-10` |

Отсюда два жёстких вывода, оба проверены на телефоне:

* **Сырой `Image` ABL не принимает вообще** — `Failed to load/authenticate boot
  image: Load Error`. Только gzip.
* **Ramdisk обязан влезть под `0x01f00000`**, иначе он перекрывает dtb. Полный
initramfs с DSP-блобами — 25.3 МиБ и не влезает, поэтому `build-initramfs.sh`
выкидывает `adsp/cdsp/venus/wlanmdsp` (~27 МиБ в распакованном виде): для шелла
они не нужны. Остаётся **11.6 МиБ**, зазор до dtb ~3.4 МиБ.

CI делает два образа, оба под `fastboot boot` — **загрузка в RAM, ничего не
прошивается**:

cmdline `console=tty0 loglevel=8 ignore_loglevel` (ABL дописывает его к
`chosen/bootargs`, последний `console=` выигрывает → fbcon).

`scripts/bootinfo.py` печатает карту `[addr, addr+size)` каждого образа и
**роняет CI**, если секции пересекаются. Текущая карта `boot.img`:

```
kernel   0x00008000 .. 0x00dba7b0  (14362544)
ramdisk  0x01000000 .. 0x01b9692f  (12151087)
dtb      0x01f00000 .. 0x01f15bcc  (89036)
```

Размеры: initramfs 11.6 МиБ, `boot.img` 25.4 МиБ.

## Как запустить на телефоне

Ничего не прошиваем — только временная загрузка в RAM:

```bash
adb reboot bootloader
fastboot boot boot.img
```

Готовый проверенный `boot.img`:
https://github.com/qualixxe/mainline-courbet/releases/download/courbet-screen-fixed/boot.img

### Готовый экранный тестовый образ

На подключённом `courbet` подтверждён `fastboot boot`-образ:
https://github.com/qualixxe/mainline-courbet/releases/download/courbet-screen-fixed/boot.img

Это локально пропатченный бинарный образ (заплатки дисплейного стека применены
в исходниках репозитория). Используй только `fastboot boot` — не прошивай разделы.
Альтернативный `boot-pmos.img` перепакован для проверки, но не проверен на телефоне.

## Локальная правка `boot.img` без GitHub Actions

Чтобы менять `initramfs` (`init`, шрифты, модули, блобы), `cmdline`, `device.dtb` или
тестировать бинарные патчи ядра прямо на ПК за ~1 секунду без 20-минутного ожидания CI:

```bash
# Распаковать готовый boot.img (достаёт Image, device.dtb, boot-meta.json и initramfs/)
python scripts/local-boot-edit.py unpack boot.img work/

# Отредактировать нужные файлы в work/initramfs/, cmdline в work/boot-meta.json,
# DTB в work/device.dtb или ядро в work/Image, затем собрать обратно:
python scripts/local-boot-edit.py repack work/ boot-test.img

# Проверить в RAM без прошивки раздела
fastboot boot boot-test.img
```

## Интеграция с postmarketOS (`pmos-courbet`)

В репо [qualixxe/pmos-courbet](https://github.com/qualixxe/pmos-courbet) лежит порт устройства courbet для postmarketOS: `device/courbet.deviceinfo`, `mkbootimg.py` (header v0, как требует courbet bootloader) и GitHub Workflow для сборки pmOS-образа.

Образ из этого репо собирает ядро 6.13.4. Если хочешь ядро 6.17 с уже исправленным экраном (все патчи дисплея из этого репо), собери гибридный `boot.img` локально:

```bash
# 1. Распаковать любой рабочий boot.img (например, из релиза courbet-screen-fixed)
python scripts/local-boot-edit.py unpack boot.img work/

# 2. Скопировать файлы из pmos-courbet (deviceinfo, init-скрипты и т.д.) в work/initramfs/
#    по желанию заменить init на свой.

# 3. Собрать гибридный образ:
python scripts/local-boot-edit.py repack work/ boot-pmos.img

# Или использовать готовый скрипт:
./scripts/build-pmos-boot.sh work/ boot-pmos.img

# 4. Запустить:
fastboot boot boot-pmos.img
```

Готовый `boot-pmos.img` (ядро 6.17 + 패тчи дисплея + Alpine initramfs) собран локально и лежит в `out/boot-pmos.img`. Его можно добавить в релиз `courbet-screen-fixed` как дополнительный ассет.

## Как проверять на телефоне

Нужен разблокированный загрузчик. **Ничего не прошиваем** — только `fastboot boot`:

```bash
adb reboot bootloader
fastboot boot boot.img          # если не пошло — fastboot boot boot-pmos.img
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

* **DTBO — подтверждено разбором дампа.** `fastboot boot` **не обходит** обработку
  DTBO. Стоковый `dtbo` courbet разобран: в нём **одна запись, все ID нулевые**
  (`id=0 rev=0 custom=[0,0,0]`), то есть wildcard — ABL применит её к любому DTB.
  Её корень объявляет `qcom,msm-id = <365 0>`, `qcom,board-id = <45 0>`, что
  **совпадает с нашим DTB**, так что оверлей точно попадёт в наше дерево.
  Внутри — 1075 узлов / 6153 свойства downstream-дерева `qcom,sdmmagpie`, а
  `__fixups__` требуют символов базового дерева: `CPU0..CPU7`, `soc`, `tlmm`,
  `mdss_mdp`, `mdss_dsi0`, `ufsphy_mem`, `ufshc_mem`, `sdhc_1/2`, `pm6150_l13` и т.д.
  **В нашем mainline DTB узла `__symbols__` нет вообще**, и этих имён в нём тоже
  нет (mainline зовёт их иначе). Разрешить fixup'ы ABL не может, при этом оверлей
  правит CPU/soc/tlmm — что и убивает ядро до console. Лечится стиранием
  (`fastboot erase dtbo`) — это **запись в телефон**, делать только осознанно и
  только имея бэкап раздела.
* **AVB.** У courbet `android,vbmeta` с `parts="vbmeta,boot,system,vendor,dtbo,recovery"`.
  Может понадобиться vbmeta с отключённой верификацией — тоже запись, тоже отдельно.
* Тач у courbet — **SPI** (`xiaomi,spits`, `qupv3_se4_spi`, irq tlmm 9, reset tlmm 8),
  а не i2c goodix/fts: те узлы в downstream — мёртвый boilerplate. Драйвера под
  `xiaomi,spits` в mainline нет, так что тач, скорее всего, не заработает.

## Ожидаемый статус железа

По wiki postmarketos для courbet на этом форке:

* **работает**: display, GPU, WiFi (WCN3990 SNOC / ath10k), battery, modem, NFC, OTG
* **не работает**: touch, audio, camera, GPS, sensors

Это ориентир, а не гарантия нашей сборки.

## Фактический статус на 2026-11-14

**Mainline загружается на courbet, шелл получен.** Проверено не по логам, а
фактически: телефон поднимает USB ACM gadget (`1d6b:0104`, serial `0123456789`),
на хосте это COM-порт, внутри интерактивный shell. Аптайм больше 90 минут,
pstore чистый. Все опыты — `fastboot boot`, то есть RAM; ни один раздел не прошит.

Работает:

* **Экран (AMOLED K9A `36_02_0a`, 1080×2400, DSC 10bpc/8bpp, cmd-mode)** — чистая картинка
  без артефактов и полос, **0 ошибок DSI FIFO**, консоль `fbcon` со шрифтом `16×32`,
  регулировка яркости через `/sys/class/backlight/ae94000.dsi.0/brightness` (`0..2047`)
* **GPU Adreno 618** — микрокод `qcom/a630_sqe.fw` и `qcom/a630_gmu.bin` подхватываются,
  DRM/MSM (`ae01000.display-controller`) инициализируется штатно
* 8 CPU, 5475 МиБ RAM, UFS — видны все разделы
* USB gadget + ACM shell (`/dev/ttyGS0`)
* ramoops/pstore, debugfs, fbdev emulation (`fb0` 32 bpp, stride 4352)

Не работает / пока вне initramfs:

* **WiFi.** В `firmware-xiaomi-courbet` лежит только `wlanmdsp.mbn`, а
  `ath10k_snoc` нужны ещё `ath10k/WCN3990/hw1.0/firmware-5.bin` и `board-2.bin`
  из linux-firmware. В initramfs они не кладутся, чтобы уложиться в лимит `< 15 МиБ`
  до адреса DTB `0x01f00000`.
* **Touch, audio, camera, GPS, sensors** — драйверов (в т.ч. `xiaomi,spits` на SPI) в mainline нет.

### Как был починен экран (3 независимых бага в mainline)

1. **Топология DSC `1:1:1` и слайс `1080×12 @ 8 bpp`.** Заводская панель
   `dsi-panel-k9a-36-02-0a-mp-dsc-cmd.dtsi` и дамп `dtbo` объявляют **один** DSC-слайс
   шириной 1080 при **8 bpp** (`qcom,display-topology = <1 1 1>`), а вендорный регистр
   `0x91` панели жёстко прошит под один слайс 1080. Mainline же резервировал 2 DSC-блока
   и делил ширину пополам, а в драйвере панели стояло `10 bpp`. Исправлено патчами
   `panel-k9a-dsc-topology.patch` и `dpu-dsc-single-slice.patch`.
2. **Шторм `FIFO_STATUS = 0x88881310` (рассинхрон 30 бит vs 24 бит на шине DPU→DSI).**
   После перехода на `1:1:1` DSI сыпал ~18.5 тыс. прерываний/сек: `CMD_MDP_FIFO_OVERFLOW` +
   `DLN0..DLN3 HS FIFO UNDERFLOW`. Причина: при включённом DSC блок DPU отдаёт сжатые байты
   в DSI по **3 байта за такт `pclk`** (24 бита), независимо от `bits_per_component = 10`.
   Из-за `MIPI_DSI_FMT_RGB101010` (30 бит) и деления на `bits_per_component * 3` в
   `dsi_adjust_pclk_for_compression()` пиксельный клок занижался на 25% (`69.58 МГц`), а
   `byte_clk` разгонялся выше скорости подкачки от DPU. Перевод формата шины в 24 бит и
   расчёт `pclk` от реальной ширины шины выставили `pclk = 85.24 МГц`, `byte_clk = 63.93 МГц` —
   ошибки FIFO исчезли полностью (`0` ошибок).
3. **Горизонтальные/боковые полосы вокруг текста (`range_max_qp[0]: 7 → 8`).**
   Стандартная таблица VESA DSC 1.1 pre-SCR в `drm_dsc_helper.c` задаёт для `10 bpc @ 8 bpp`
   значение `rc_range_params[0].range_max_qp = 7`. В downstream-драйвере Qualcomm/Xiaomi
   (`dsi_panel.c`) и заводском PPS панели K9A нулевой диапазон переопределён в **`8`**
   (регистр `dsc_0 + 0xb0 = 0x8`). При `7` на плоских однотонных участках (фон консоли рядом
   с глифами) возникали полосы переполнения/квантования DSC. Патч
   `dsi-dsc-10bpc-8bpp-qp0.patch` синхронизирует и PPS панели, и `DSC_RANGE_MAX_QP_0` в DPU1
   со значением `8` — полосы полностью пропали.

### Что решило загрузку

Стоковый `dtbo` (разбор ниже, в «Подводных камнях»). После `fastboot erase dtbo`
ядро дошло до console и подняло gadget. Бэкап раздела сохранён локально
(33554432 байт, sha256 `82d9143b…`); **пока dtbo стёрт, стоковая Android-прошивка
может не загружаться корректно** — восстановление это запись в телефон и
делается отдельно, с явного согласия.

Отброшенные по пути гипотезы, чтобы не проверять их дважды: перекрытие секций
(карта чистая), «16K pages» (`flags=0xa` и у stock тоже, `ARM64_4K_PAGES=y`),
анти-rollback по `os_version`, рассинхрон video/cmd-режима (msm host смотрит
только на бит `MIPI_DSI_MODE_VIDEO`), отсутствие PMIC-регуляторов, автогашение
консоли (`consoleblank=0`), патч dcs_write_seq, сбой инициализации панели.

**Повторно проверено на подключённом Xiaomi Mi 11 Lite 4G:** образ загружен через
`fastboot boot` (без прошивки раздела). Панель показывает текст на синем фоне;
после оверрайда `range_max_qp[0] = 8` пользователь подтвердил, что полосы исчезли.
В serial-shell подтверждены `pclk = 85.24 МГц`, `byte_clk = 63.93 МГц`, включённая
подсветка и отсутствие прежнего шторма FIFO.

## Ссылки

* https://github.com/sm7150-mainline/linux — основное community-дерево SM7150
* https://github.com/kevinwidjaja21/linux/tree/courbet_main — 6.17 с courbet dts + панель
* https://github.com/sm7150-mainline/firmware-xiaomi-courbet — блобы
* https://gitlab.postmarketos.org/kevinwidjaja21/pmaports — ветка `courbet_stable`
* https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/courbet-r-oss — downstream 4.14
* https://github.com/Aciss21/kernel_xiaomi_sm6150/tree/aosp — downstream courbet
  4.14.357-openela, источник заводской конфигурации панели:
  `arch/arm64/boot/dts/qcom/xiaomi/courbet/dsi-panel-k9a-36-02-0a-mp-dsc-cmd.dtsi`
  и `drivers/gpu/drm/msm/dsi-staging/` (ветки `aosp`/`oem`, не `16`)
* https://wiki.postmarketos.org/wiki/Xiaomi_Mi_11_Lite_4G_(xiaomi-courbet)
