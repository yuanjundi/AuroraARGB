"""显卡 V2 包：灯珠数量扫描。

V2 包头 AA EF 01 04 88 NN，其中 NN 疑似灯珠数（OpenRGB 固定写 0x26 = 38）。
本工具按不同 NN 构造整包，每档只点亮「第 1 颗红、其余全黑」，
中间插入 V1 全黑做参照，便于人眼分辨。

若能出现单个红点，说明该灯珠数下 V2 通道成立。

用法：
    python gpu_v2_sweep.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backends.gpu_colorful import ColorfulGpu  # noqa: E402

COUNTS = [12, 18, 24, 30, 38]
HOLD = 3.0          # 每档 V2 保持
BLACK = 1.2         # 黑场间隔


def packet_v2_n(count: int, colors) -> bytes:
    """按指定灯珠数构造 V2 包：6 字节头 + count*3 + 2 字节校验。"""
    body = bytearray([0xAA, 0xEF, 0x01, 0x04, 0x88, count & 0xFF])
    for i in range(count):
        c = colors[i] if i < len(colors) else (0, 0, 0)
        body.extend((c[0] & 0xFF, c[1] & 0xFF, c[2] & 0xFF))
    crc = sum(body) & 0xFFFF
    body.extend((crc & 0xFF, (crc >> 8) & 0xFF))
    return bytes(body)


def main() -> int:
    with ColorfulGpu() as gpu:
        if not gpu.open() or not gpu.handshake():
            print("初始化失败:", gpu.last_error)
            return 1
        print("设备:", gpu.gpu_name)
        print("每档只点亮第 1 颗红，其余全黑；中间插黑场\n")

        for n in COUNTS:
            pkt = packet_v2_n(n, [(255, 0, 0)])
            gpu.set_color(0, 0, 0)          # 黑场参照
            time.sleep(BLACK)
            gpu.write(pkt)
            print("  灯珠数 %-3d 包长 %-4d -> 已发送" % (n, len(pkt)))
            time.sleep(HOLD)

        print("\n最后全黑，再恢复青色…")
        gpu.set_color(0, 0, 0)
        time.sleep(BLACK)
        gpu.set_color(0, 190, 255)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
