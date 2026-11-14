"""显卡灯带：命令字节扫描。

已知 0x12 = 设色（AA EF 12 03 01 FF R G B CRC）。
本工具依次换用相邻命令字节，每段 2.5 秒，看是否出现「自己会动」的效果。

安全说明：只发 11 字节短包，不写固件、不改配置；万一器件不理，最长重启恢复。

用法：
    python gpu_cmd_scan.py [开始] [结束] [每段秒]
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backends.gpu_colorful import ColorfulGpu  # noqa: E402


def packet(cmd: int, r: int, g: int, b: int) -> bytes:
    body = [0xAA, 0xEF, cmd & 0xFF, 0x03, 0x01, 0xFF, r, g, b]
    crc = sum(body) & 0xFFFF
    return bytes(body + [crc & 0xFF, (crc >> 8) & 0xFF])


def main() -> int:
    lo = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x10
    hi = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x1F
    hold = float(sys.argv[3]) if len(sys.argv) > 3 else 2.5

    with ColorfulGpu() as gpu:
        if not gpu.open() or not gpu.handshake():
            print("初始化失败:", gpu.last_error)
            return 1
        print("设备:", gpu.gpu_name)
        print("扫描命令 0x%02X..0x%02X，每段 %.1f 秒\n" % (lo, hi, hold))

        for cmd in range(lo, hi + 1):
            st = gpu.write(packet(cmd, 255, 0, 0))
            print("  cmd 0x%02X  状态 %s   包 %s" % (
                cmd, "OK" if st == 0 else st, packet(cmd, 255, 0, 0).hex(" ").upper()))
            time.sleep(hold)

        print("\n恢复青色（0x12）…")
        gpu.set_color(0, 190, 255)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
