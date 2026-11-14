"""V2 逐颗设色实验 —— 122 字节包，最多 38 颗灯珠。

用法：
    python gpu_v2_test.py count        只点亮第 0 颗，其余全黑（最关键的一测）
    python gpu_v2_test.py gradient     38 颗红→蓝渐变
    python gpu_v2_test.py split        前 19 颗红、后 19 颗蓝
    python gpu_v2_test.py uniform 255 0 255
    python gpu_v2_test.py restore      回到 V1 整条单色（白）

判读方法：
    count    → 只有一个点亮 = 逐颗控制成立，还能看出灯带哪端是第 0 颗
             → 整条同色     = 只取了第一颗的颜色，逐颗控制不成立
             → 全黑         = 这个型号不认 V2 包
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backends.gpu_colorful import (  # noqa: E402
    ColorfulGpu, build_packet_v2, V2_MAX_LEDS,
)

WHITE = (255, 255, 255)


def lerp(a, b, t):
    return int(round(a + (b - a) * t))


def pattern(name: str, args):
    n = V2_MAX_LEDS
    if name == "count":
        colors = [(0, 0, 0)] * n
        colors[0] = (0, 255, 0)          # 第一颗绿色，最扎眼
        return colors
    if name == "gradient":
        return [(lerp(255, 0, i / (n - 1)),
                 lerp(0, 120, i / (n - 1)),
                 lerp(0, 255, i / (n - 1))) for i in range(n)]
    if name == "split":
        return [(255, 0, 0)] * (n // 2) + [(0, 0, 255)] * (n - n // 2)
    if name == "uniform":
        r, g, b = (int(x) for x in (args + ["255", "255", "255"])[:3])
        return [(r, g, b)] * n
    return None


def main() -> int:
    if not sys.argv[1:]:
        print(__doc__)
        return 1

    name = sys.argv[1].lower()
    print("=" * 58)
    print(" V2 逐颗设色实验 · %s" % name)
    print("=" * 58)

    with ColorfulGpu() as gpu:
        if not gpu.open():
            print("!! 初始化失败:", gpu.last_error)
            return 1
        if not gpu.handshake():
            print("!! 握手失败:", gpu.last_error)
            return 2
        print("显卡:", gpu.gpu_name, "| 握手通过")

        if name == "restore":
            ok = gpu.set_color(*WHITE)
            print("V1 恢复为白色:", ok)
            return 0 if ok else 3

        colors = pattern(name, sys.argv[2:])
        if colors is None:
            print("!! 未知模式:", name)
            return 1

        pkt = build_packet_v2(colors)
        print("包长 %d 字节（期望 122）" % len(pkt))
        print("头部:", pkt[:8].hex(" ").upper())
        print("尾部:", pkt[-8:].hex(" ").upper())
        print("灯珠 %d 颗，前 3 颗: %s" % (len(colors), colors[:3]))

        ok = gpu.set_colors(colors)
        print("\n写入结果:", ok, gpu.last_error)
        if ok:
            print("\n去看显卡灯带，然后把看到的告诉我。")
            print("恢复：python gpu_v2_test.py restore")
        return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
