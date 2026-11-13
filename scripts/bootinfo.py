#!/usr/bin/env python3
"""Dump an Android boot image header and fail if the load sections overlap."""
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
    hdr = dict(zip(NAMES, struct.unpack_from("<10I", d, 8)))
    print(f"== {path}")
    for name in NAMES:
        print(f"  {name:16} {hdr[name]:#x} ({hdr[name]})")
    print(f"  name             {cstr(d[48:64])!r}")
    print(f"  cmdline          {cstr(d[64:576])}")

    ver = hdr["header_version"]
    sections = [
        ("kernel", hdr["kernel_addr"], hdr["kernel_size"]),
        ("ramdisk", hdr["ramdisk_addr"], hdr["ramdisk_size"]),
    ]
    if ver >= 1:
        print(f"  header_size      {struct.unpack_from('<I', d, 1644)[0]}")
    if ver >= 2:
        dtb_size = struct.unpack_from("<I", d, 1648)[0]
        dtb_addr = struct.unpack_from("<Q", d, 1652)[0]
        print(f"  dtb_size         {dtb_size}")
        print(f"  dtb_addr         {dtb_addr:#x}")
        if dtb_size:
            sections.append(("dtb", dtb_addr, dtb_size))

    print("  --- load layout ---")
    for name, addr, size in sections:
        print(f"  {name:8} {addr:#010x} .. {addr + size:#010x}  ({size} bytes)")

    bad = []
    for i, (n1, a1, s1) in enumerate(sections):
        for n2, a2, s2 in sections[i + 1:]:
            if s1 and s2 and a1 < a2 + s2 and a2 < a1 + s1:
                bad.append(
                    f"{n1} [{a1:#x},{a1 + s1:#x}) overlaps "
                    f"{n2} [{a2:#x},{a2 + s2:#x})"
                )
    if bad:
        for b in bad:
            print(f"  FATAL: {b}")
        return 1
    print("  layout OK: no overlapping sections")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: bootinfo.py boot.img [boot2.img ...]")
    sys.exit(max(main(p) for p in sys.argv[1:]))