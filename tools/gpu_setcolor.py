"""给七彩虹显卡灯带设色 —— 自己实现的驱动，走 NVAPI I2C。

用法：
    python gpu_setcolor.py            只握手，不写颜色（安全检查）
    python gpu_setcolor.py 255 0 255  设成品红
    python gpu_setcolor.py 0 0 0      关灯
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backends.gpu_colorful import ColorfulGpu, build_packet  # noqa: E402


def main() -> int:
    args = sys.argv[1:]

    print("=" * 58)
    print(" Colorful GPU 灯控 · 自研驱动")
    print("=" * 58)

    with ColorfulGpu() as gpu:
        if not gpu.ready and not gpu.last_error:
            pass
        if not gpu.open():
            print("!! 初始化失败:", gpu.last_error)
            return 1

        print("显卡:", gpu.gpu_name or "(未知)")

        if not gpu.handshake():
            print("!! 握手失败:", gpu.last_error)
            print("   说明这块卡可能不是同一套协议，或灯控不在 0x61。")
            return 2
        print("握手: 通过（响应头 AA EF 81，确认是七彩虹灯控）")

        if len(args) < 3:
            print("\n只做了握手，没有写入颜色。")
            print("要设色请给三个 0-255 的数值，例如：python gpu_setcolor.py 255 0 255")
            return 0

        try:
            r, g, b = (max(0, min(255, int(a))) for a in args[:3])
        except ValueError:
            print("!! 颜色值必须是整数")
            return 1

        pkt = build_packet(r, g, b)
        print("\n将要写入的 11 字节:")
        print("   " + pkt.hex(" ").upper())

        if not gpu.set_color(r, g, b):
            print("!! 写入失败:", gpu.last_error)
            return 3

        print("写入成功 -> RGB(%d, %d, %d)" % (r, g, b))
        print("\n去看一眼显卡侧面的 iGame 灯带，颜色变了吗？")
        return 0


if __name__ == "__main__":
    sys.exit(main())
