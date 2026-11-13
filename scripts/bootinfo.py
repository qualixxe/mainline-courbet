#!/usr/bin/env python3
"""Dump an Android boot image header so we can prove the layout we asked for."""
import struct
import sys

NAMES = [
    "kernel_size", "kernel_addr", "ramdisk_size", "ramdisk_addr",
    "second_size", "second_addr", "tags_addr", "page_size",
    "header_version", "os_version",
]


def cstr(buf):
    return buf.split(b"\x00")[0].decode(errors="replace")


def main(path):
    with open(path, "rb") as f:
        d = f.read(1664)
    if d[:8] != b"ANDROID!":
        raise SystemExit(f"{path}: bad magic {d[:8]!r}")
    print(f"== {path}")
    for name, val in zip(NAMES, struct.unpack_from("<10I", d, 8)):
        print(f"  {name:16} {val:#x} ({val})")
    print(f"  name             {cstr(d[48:64])!r}")
    print(f"  cmdline          {cstr(d[64:576])}")
    print(f"  header_size@1644 {struct.unpack_from('<I', d, 1644)[0]}")
    print(f"  dtb_size@1648    {struct.unpack_from('<I', d, 1648)[0]}")
    print(f"  dtb_addr@1652    {struct.unpack_from('<Q', d, 1652)[0]:#x}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        main(p)