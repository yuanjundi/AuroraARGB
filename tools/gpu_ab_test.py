"""A/B 交替测试 —— 用最少的记忆负担判断「灯珠区间」假设。

每隔 interval 秒在两种包之间切换：

    A = 12 03 01 FF + 红色   （整条红）
    B = 12 03 01 01 + 蓝色   （区间假设成立 → 只亮一颗蓝点）

三种可能的观察结果，各自指向不同结论：

    整条 红↔蓝 来回闪        → 01/02 不是区间，被忽略（假设不成立）
    整条红 ↔ 一颗蓝点        → 区间成立，逐颗控制可用！
    一直是红，没有蓝         → B 包被忽略
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backends.gpu_colorful import ColorfulGpu  # noqa: E402


def build(cmd, ln, a, b, r, g, bl):
    body = [0xAA, 0xEF, cmd & 0xFF, ln & 0xFF, a & 0xFF, b & 0xFF,
            r & 0xFF, g & 0xFF, bl & 0xFF]
    crc = sum(body) & 0xFFFF
    return bytes(body + [crc & 0xFF, (crc >> 8) & 0xFF])


def main() -> int:
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    cycles = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    A = ("A 整条红", build(0x12, 0x03, 0x01, 0xFF, 255, 0, 0))
    B = ("B 单颗蓝", build(0x12, 0x03, 0x01, 0x01, 0, 0, 255))

    with ColorfulGpu() as gpu:
        if not gpu.open() or not gpu.handshake():
            print("!! 初始化/握手失败:", gpu.last_error)
            return 1

        t0 = time.time()
        print("显卡:", gpu.gpu_name, "| 每 %.1f 秒切换一次，共 %d 轮（约 %.0f 秒）"
              % (interval, cycles, interval * cycles * 2))

        for i in range(cycles):
            for label, pkt in (A, B):
                gpu.write(pkt)
                print("[%5.1fs] %-10s %s" % (time.time() - t0, label, pkt[2:6].hex(" ").upper()),
                      flush=True)
                time.sleep(interval)

        gpu.set_color(255, 0, 0)
        print("结束，停在整条红。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
