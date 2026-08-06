#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_assets.py —— 把碎片 85ac 注入对钩函数.png 的 tEXt 信息块

用法:
    python3 make_assets.py <输入png> <输出png> [碎片值]

默认把 对钩函数.png -> static/tick.png，碎片 85ac。
"""
import struct
import sys
import zlib
from pathlib import Path

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("对钩函数.png")
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("static") / "tick.png"
FRAG = sys.argv[3] if len(sys.argv) > 3 else "85ac"


def add_text_chunk(png: bytes, keyword: str, text: str) -> bytes:
    """在 IEND 前插入一个 tEXt 块。"""
    payload = keyword.encode("utf-8") + b"\x00" + text.encode("utf-8")
    chunk = (
        struct.pack(">I", len(payload))
        + b"tEXt"
        + payload
        + struct.pack(">I", zlib.crc32(b"tEXt" + payload) & 0xFFFFFFFF)
    )
    iend = png.rfind(b"IEND")
    if iend == -1:
        raise ValueError("不是合法的 PNG 文件（找不到 IEND 块）")
    return png[: iend - 4] + chunk + png[iend - 4 :]


def main() -> None:
    DST.parent.mkdir(parents=True, exist_ok=True)
    raw = SRC.read_bytes()
    out = add_text_chunk(raw, "tick", FRAG)
    DST.write_bytes(out)
    print(f"[OK] 已注入碎片 {FRAG} -> {DST} ({len(out)} bytes)")


if __name__ == "__main__":
    main()
