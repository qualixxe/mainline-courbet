#!/usr/bin/env python3
"""
Local boot.img unpacker / patcher / repacker for Xiaomi Mi 11 Lite 4G (courbet).
Lets you edit initramfs scripts, kernel cmdline, DTB, or binary-patch Image
on Windows/Linux in ~1 second without rebuilding the kernel on GitHub Actions.

Usage:
  python scripts/local-boot-edit.py unpack boot.img workdir/
  python scripts/local-boot-edit.py repack workdir/ boot-new.img
"""

import argparse
import gzip
import io
import json
import os
import struct
import subprocess
import sys
import zlib

BOOT_MAGIC = b"ANDROID!"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"


def align_up(n: int, page: int) -> int:
    return (n + page - 1) & ~(page - 1)


def read_cpio_entries(raw: bytes):
    entries = []
    pos = 0
    while pos + 110 <= len(raw):
        if raw[pos : pos + 6] != b"070701":
            break
        hdr = raw[pos : pos + 110].decode("ascii")
        mode = int(hdr[14:22], 16)
        filesize = int(hdr[54:62], 16)
        namesize = int(hdr[94:102], 16)
        name_start = pos + 110
        name = raw[name_start : name_start + namesize - 1].decode("utf-8", "replace")
        data_start = align_up(name_start + namesize, 4)
        data = raw[data_start : data_start + filesize]
        pos = align_up(data_start + filesize, 4)
        if name == "TRAILER!!!":
            break
        entries.append((name, mode, data))
    return entries


def build_cpio(entries) -> bytes:
    out = bytearray()
    ino = 300000

    def add_entry(name: str, mode: int, data: bytes, nlink: int = 1):
        nonlocal ino
        name_b = name.encode("utf-8") + b"\x00"
        hdr = (
            "070701"
            f"{ino:08x}{mode:08x}{0:08x}{0:08x}{nlink:08x}{0:08x}"
            f"{len(data):08x}{0:08x}{0:08x}{0:08x}{0:08x}"
            f"{len(name_b):08x}{0:08x}"
        ).encode("ascii")
        ino += 1
        out.extend(hdr)
        out.extend(name_b)
        while len(out) % 4:
            out.append(0)
        out.extend(data)
        while len(out) % 4:
            out.append(0)

    for name, mode, data in entries:
        nlink = 2 if (mode & 0o170000) == 0o040000 else 1
        add_entry(name, mode, data, nlink)

    add_entry("TRAILER!!!", 0, b"", 1)
    while len(out) % 512:
        out.append(0)
    return bytes(out)


def split_image_gz_dtb(kernel_blob: bytes):
    dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
    image_raw = dec.decompress(kernel_blob)
    image_raw += dec.flush()
    dtb_part = dec.unused_data
    return image_raw, dtb_part



def cmd_unpack(args):
    os.makedirs(args.workdir, exist_ok=True)
    with open(args.boot_img, "rb") as f:
        buf = f.read()

    if buf[:8] != BOOT_MAGIC:
        raise RuntimeError("Not an ANDROID! boot image")

    (
        kernel_size,
        kernel_addr,
        ramdisk_size,
        ramdisk_addr,
        second_size,
        second_addr,
        tags_addr,
        page_size,
        header_version,
        _os_version,
    ) = struct.unpack_from("<10I", buf, 8)
    name = buf[48:64].split(b"\x00", 1)[0].decode("utf-8", "replace")
    cmdline = buf[64 : 64 + 512].split(b"\x00", 1)[0].decode("utf-8", "replace")
    extra_cmdline = buf[608 : 608 + 1024].split(b"\x00", 1)[0].decode("utf-8", "replace")
    full_cmdline = cmdline + extra_cmdline

    off = page_size
    kernel_blob = buf[off : off + kernel_size]
    off += align_up(kernel_size, page_size)
    ramdisk_blob = buf[off : off + ramdisk_size]
    off += align_up(ramdisk_size, page_size)
    off += align_up(second_size, page_size)

    dtb_sep = b""
    if header_version >= 2:
        (recovery_dtbo_size, _lo, _hi, _hdr_sz, dtb_size, dtb_addr) = struct.unpack_from(
            "<IIQIIQ", buf, 1632
        )
        off += align_up(recovery_dtbo_size, page_size)
        dtb_sep = buf[off : off + dtb_size]
    else:
        dtb_addr = 0

    image_raw, dtb_appended = split_image_gz_dtb(kernel_blob)
    dtb_effective = dtb_appended if dtb_appended else dtb_sep
    with open(os.path.join(args.workdir, "Image"), "wb") as f:
        f.write(image_raw)
    with open(os.path.join(args.workdir, "device.dtb"), "wb") as f:
        f.write(dtb_effective)

    entries = read_cpio_entries(gzip.decompress(ramdisk_blob))
    rd_root = os.path.join(args.workdir, "initramfs")
    os.makedirs(rd_root, exist_ok=True)
    manifest = []
    for rel, mode, data in entries:
        manifest.append({"path": rel, "mode": oct(mode)})
        target = os.path.join(rd_root, *rel.split("/"))
        ftype = mode & 0o170000
        if ftype == 0o040000:
            os.makedirs(target, exist_ok=True)
        elif ftype == 0o120000:
            manifest[-1]["symlink"] = data.decode("utf-8", "replace")
        elif ftype == 0o100000:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as out_f:
                out_f.write(data)

    meta = {
        "header_version": header_version,
        "page_size": page_size,
        "base": 0,
        "kernel_offset": kernel_addr,
        "ramdisk_offset": ramdisk_addr,
        "second_offset": second_addr,
        "tags_offset": tags_addr,
        "dtb_offset": dtb_addr,
        "appended_dtb": len(dtb_appended) > 0,
        "separate_dtb": len(dtb_sep) > 0,
        "board": name,
        "cmdline": full_cmdline,
        "cpio_entries": manifest,
    }
    with open(os.path.join(args.workdir, "boot-meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"Unpacked {args.boot_img} -> {args.workdir} (Image={len(image_raw)}B, DTB={len(dtb_effective)}B)")


def cmd_repack(args):
    with open(os.path.join(args.workdir, "boot-meta.json"), "r", encoding="utf-8") as f:
        meta = json.load(f)
    with open(os.path.join(args.workdir, "Image"), "rb") as f:
        image_raw = f.read()
    with open(os.path.join(args.workdir, "device.dtb"), "rb") as f:
        dtb_raw = f.read()

    gz_buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=gz_buf, compresslevel=6, mtime=0) as gz:
        gz.write(image_raw)
    kernel_blob = gz_buf.getvalue() + (dtb_raw if meta.get("appended_dtb", True) else b"")

    rd_root = os.path.join(args.workdir, "initramfs")
    entries, seen = [], set()
    for item in meta["cpio_entries"]:
        rel, mode = item["path"], int(item["mode"], 8)
        seen.add(rel)
        ftype = mode & 0o170000
        if ftype == 0o040000:
            entries.append((rel, mode, b""))
        elif ftype == 0o120000:
            entries.append((rel, mode, item["symlink"].encode("utf-8")))
        else:
            host_path = os.path.join(rd_root, *rel.split("/"))
            with open(host_path, "rb") as rf:
                entries.append((rel, mode, rf.read()))

    for root, _dirs, files in os.walk(rd_root):
        rel_dir = os.path.relpath(root, rd_root).replace("\\", "/")
        if rel_dir != "." and rel_dir not in seen:
            entries.append((rel_dir, 0o040755, b""))
            seen.add(rel_dir)
        for fn in files:
            rel_file = fn if rel_dir == "." else f"{rel_dir}/{fn}"
            if rel_file not in seen:
                with open(os.path.join(root, fn), "rb") as rf:
                    fmode = 0o100755 if rel_file.endswith((".sh", "init")) else 0o100644
                    entries.append((rel_file, fmode, rf.read()))
                seen.add(rel_file)

    rd_gz = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=rd_gz, compresslevel=9, mtime=0) as gz:
        gz.write(build_cpio(entries))

    tmp_k = os.path.join(args.workdir, "_tmp_Image.gz-dtb")
    tmp_r = os.path.join(args.workdir, "_tmp_initramfs.cpio.gz")
    with open(tmp_k, "wb") as f:
        f.write(kernel_blob)
    with open(tmp_r, "wb") as f:
        f.write(rd_gz.getvalue())

    mkbootimg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mkbootimg.py")
    cmd = [
        sys.executable, mkbootimg,
        "--header_version", str(meta["header_version"]),
        "--kernel", tmp_k, "--ramdisk", tmp_r,
        "--base", hex(meta["base"]),
        "--kernel_offset", hex(meta["kernel_offset"]),
        "--ramdisk_offset", hex(meta["ramdisk_offset"]),
        "--second_offset", hex(meta["second_offset"]),
        "--tags_offset", hex(meta["tags_offset"]),
        "--dtb_offset", hex(meta["dtb_offset"]),
        "--pagesize", str(meta["page_size"]),
        "--cmdline", meta["cmdline"],
        "-o", args.out_img,
    ]
    if meta.get("separate_dtb"):
        cmd.extend(["--dtb", os.path.join(args.workdir, "device.dtb")])
    subprocess.check_call(cmd)
    os.remove(tmp_k)
    os.remove(tmp_r)
    print(f"Repacked -> {args.out_img} ({os.path.getsize(args.out_img)} bytes)")


def main():
    ap = argparse.ArgumentParser(description="Unpack and repack courbet boot.img locally")
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("unpack")
    u.add_argument("boot_img")
    u.add_argument("workdir")
    u.set_defaults(func=cmd_unpack)
    r = sub.add_parser("repack")
    r.add_argument("workdir")
    r.add_argument("out_img")
    r.set_defaults(func=cmd_repack)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
