# mainline-courbet

Mainline Linux для **Xiaomi Mi 11 Lite 4G** (`courbet`, M2101K9AG, Qualcomm **SM7150** /
Snapdragon 732G). Сборка целиком в GitHub Actions, локально ничего не нужно.

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
   модули ядра + firmware courbet. Firmware-репо кладёт блобы в
   `qcom/sm7150/courbet/`, а dts просит `qcom/sm7150/xiaomi/courbet/` — делаем оба пути.
   Исключены `modem.mbn` (62 MiB) и DSP/venus/wlan-блобы (~27 MiB): ramdisk должен
   влезть под адрес dtb `0x01f00000`.
7. `scripts/mkbootimg.py` — вендоренный AOSP mkbootimg.

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

| файл | header | kernel | dtb | статус |
|---|---|---|---|---|
| `boot.img` | v2 | `Image.gz` | отдельной секцией | **основной**, один в один как stock |
| `boot-pmos.img` | v1 | `Image.gz` | приклеен к концу kernel | конвенция postmarketOS; ABL принимает, но не загрузилось |

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

## Как запустить сборку

```bash
gh workflow run build.yml -R qualixxe/mainline-courbet
gh run watch -R qualixxe/mainline-courbet
```

Inputs: `kernel_repo`, `kernel_ref` (например `sm7150-mainline/linux` + `v6.13.4` как
fallback), `with_firmware`, `cmdline`. Результат — GitHub Release с `boot.img`,
`boot-pmos.img`, `initramfs.cpio.gz`, `Image.gz`, dtb, `config`, `MANIFEST.txt`,
`SHA256SUMS.txt`, `build.log`.

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

* 8 CPU, 5475 МиБ RAM, UFS — видны все разделы
* USB gadget + ACM shell (`/dev/ttyGS0`)
* DRM/DPU зарегистрирован, панель K9A привязана на 1080x2400, подсветка включена
* ramoops/pstore, debugfs, fbdev emulation (fb0 32 bpp, stride 4352)

Не работает:

* **Экран чёрный.** Панель инициализируется без единой ошибки, DSI PLL на
  рантайме залочен (бит `PLL_UNLOCKED` в `dsi_err_worker` не выставлен), но DSI
  сыплет FIFO underflow (`status=4`), а DPU — `wait_for_idle ... ret:-110` и
  `enc33 frame done timeout` каждые ~88 мс. Корень найден сравнением с
  downstream-ядром courbet (`Aciss21/kernel_xiaomi_sm6150`, ветка `aosp`,
  4.14.357-openela): заводская панель
  `dsi-panel-k9a-36-02-0a-mp-dsc-cmd.dtsi` объявляет **один** DSC-слайс
  шириной 1080 при **8 bpp**, а топология в dtbo — `<1 1 1>`, то есть один
  LM, один DSC, один INTF. Mainline же всегда резервирует **два** DSC-блока
  (`dpu_encoder_update_topology`, условие `catalog->dsc_count >= 2`; у SM7150
  их два) и делит строку пополам — `enc_ip_w = intf_ip_w / num_dsc` в
  `dpu_encoder_prep_dsc`, — тогда как `dpu_hw_dsc_config` пишет `slice_width`
  в `DSC_SLICE` без деления. Панель при этом получает PPS из `prepare()`, а её
  вендорный регистр DSC `0x91` прошит заводским payload'ом на один слайс
  1080 — переписать его нельзя, кодировка полей неизвестна. Значит подгонять
  надо DPU, а не панель. Два патча:
  * `panel-k9a-dsc-topology.patch` — 1080 / 1 слайс / **8 bpp** (было 10);
  * `dpu-dsc-single-slice.patch` — при `slice_count == 1` DPU берёт один
    DSC-блок; `dpu_crtc_get_topology` тогда даёт `num_lm = 1`
    (`1080 > MAX_HDISPLAY_SPLIT` ложно), то есть ровно заводские 1:1:1.

  Первая попытка шла в обратную сторону (540 / 2 слайса, как в
  `panel-visionox-r66451.c`) — **проверено на телефоне, поток ошибок не
  прекратился**: DPU и DSI соглашались друг с другом, но панель нет.
* **GPU.** Adreno 618 грузит микрокод SQE из `qcom/a630_sqe.fw`, которого нет в
  репозитории блобов courbet. Добавлен из linux-firmware, на телефоне
  подтверждено: `loaded qcom/a630_sqe.fw from new location`. Следом не хватало
  `qcom/a630_gmu.bin` (`-2`) — добавлен тоже.
* **WiFi.** В `firmware-xiaomi-courbet` лежит только `wlanmdsp.mbn`, а
  `ath10k_snoc` нужны ещё `ath10k/WCN3990/hw1.0/firmware-5.bin` и `board-2.bin`
  из linux-firmware. В initramfs они не кладутся, так что WiFi не поднимется,
  даже если драйвер инициализируется. Для bring-up это не нужно — шелл идёт по
  USB ACM.
* **Touch, audio, camera, GPS, sensors** — драйверов в mainline нет.

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

Проверено замерами на живом телефоне (релиз 9):

* **DSI PLL на рантайме исправен.** `clk_summary`: `dsi0vco_clk` 1043710693 Гц,
  `dsi0_pll_bit_clk` 521855347, `dsi0_phy_pll_out_byteclk` 65231918,
  `dispcc_mdss_pclk0_clk` 69580713 — все enable=Y. Ошибка
  `DSI PLL(0) lock failed, status=0x00000000` на probe — артефакт
  `clk_core_reparent_orphans_nolock` до включения PHY, не корень.
* **TE замuxен верно**: `pin 10 (GPIO_10): device ae94000.dsi.0 function
  mdp_vsync`.
* **Прерывания**: `dsi_isr` 5 566 665 за 5 минут (~18.5 тыс/сек), MDP 7702.
  Ошибка DSI непрерывная, а не раз в кадр — то есть условие в железе
  персистентное, а не привязано к передаче кадра.
* Заводской dtbo: `qcom,display-topology = <1 1 1>` (один LM/DSC/INTF),
  `qcom,mdss-dsi-panel-clockrate = <652000000>`; в dtsi downstream — 682000000.
  Расхождение с нашими 522 МГц объяснено: downstream берёт bit clk **прямо из
  DT** (`dsi_display.c`, `dsi_display_update_dsi_bitrate(display,
  mode->timing.clk_rate_hz)`), а mainline **вычисляет** его из таймингов и bpp
  (`dsi_adjust_pclk_for_compression` → `dsi_byte_clk_get_rate`). Полосы при
  522 МГц хватает: DPU отдаёт `pclk × 3` = 208.7 МБ/с, DSI забирает
  `byte_clk × 4 lanes` = 260.9 МБ/с, панели нужно 1080 × 2400 × 60 =
  155.5 МБ/с. Так что это не корень, а следствие другой формулы.
* Widebus отброшен: `msm_dsi_host_is_wide_bus_enabled()` и
  `dpu_encoder_is_widebus_enabled()` — один и тот же источник, DPU и DSI
  выбирают 3 или 6 байт на pclk согласованно.

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
