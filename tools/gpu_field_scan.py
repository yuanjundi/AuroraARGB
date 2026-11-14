"""V1 包控制字节扫描 —— 弄清楚 AA EF 12 03 01 FF 里后四个字节各管什么。

V1 包结构：
    AA EF | 12 | 03 | 01 | FF | R G B | CRC_L CRC_H
            ↑    ↑    ↑    ↑
          命令  长度  ?    ?

假设候选：
    · 「01」可能是模式号（1 = 静态直写），换成 2/3/4 也许能触发硬件灯效
    · 「FF」可能是亮度或速度

这个脚本按时间线依次写入不同的控制字节，每步停留几秒，你只需要盯着灯带看
哪一步出现了变化。全程只用 V1 包，任何一步都能用最后一步恢复。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backends.gpu_colorful import ColorfulGpu  # noqa: E402


def build(cmd: int, ln: int, a: int, b: int, r: int, g: int, bl: int) -> bytes:
    body = [0xAA, 0xEF, cmd & 0xFF, ln & 0xFF, a & 0xFF, b & 0xFF,
            r & 0xFF, g & 0xFF, bl & 0xFF]
    crc = sum(body) & 0xFFFF
    return bytes(body + [crc & 0xFF, (crc >> 8) & 0xFF])


# (标签, cmd, len, a, b, r, g, bl)
# 核心假设：「a b」是灯珠区间 [起始, 结束]，01 FF = 整条
STEPS = [
    ("① 基准 01 FF：整条红",     0x12, 0x03, 0x01, 0xFF, 255, 0, 0),
    ("② 01 01：只第 1 颗？",     0x12, 0x03, 0x01, 0x01, 255, 0, 0),
    ("③ 01 04：前 4 颗？",       0x12, 0x03, 0x01, 0x04, 255, 0, 0),
    ("④ 10 20：第 16-32 颗？",   0x12, 0x03, 0x10, 0x20, 255, 0, 0),
    ("⑤ 字节5=0x40（亮度？）",    0x12, 0x03, 0x01, 0x40, 255, 0, 0),
    ("⑥ 恢复 01 FF：整条红",     0x12, 0x03, 0x01, 0xFF, 255, 0, 0),
]


def main() -> int:
    hold = float(sys.argv[1]) if len(sys.argv) > 1 else 3.5

    with ColorfulGpu() as gpu:
        if not gpu.open() or not gpu.handshake():
            print("!! 初始化/握手失败:", gpu.last_error)
            return 1
        print("显卡:", gpu.gpu_name)
        print("每步停留 %.1f 秒，总计约 %.0f 秒\n" % (hold, hold * len(STEPS)))

        t0 = time.time()
        for i, (label, cmd, ln, a, b, r, g, bl) in enumerate(STEPS, 1):
            pkt = build(cmd, ln, a, b, r, g, bl)
            st = gpu.write(pkt)
            print("[%4.1fs] 第 %d 步  %-22s  %s" % (
                time.time() - t0, i, label, pkt[2:6].hex(" ").upper()))
            time.sleep(hold)

        print("\n扫描完成，最后停在「基准：静态红」。")
        print("回想一下：哪几步和基准看起来不一样？")
    return 0


if __name__ == "__main__":
    sys.exit(main())
