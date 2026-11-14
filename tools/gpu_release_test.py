"""显卡灯带：验证「停手后固件动画是否自动回来」。

流程：
    A  写纯红，保持 12 秒      —— 确认现在是静态接管状态
    B  完全不写，静置 25 秒    —— 关键观察窗口
    C  写纯绿                  —— 证明器件仍在线

如果 B 段里灯自己变回彩虹/开始流动，说明可以做「放手」开关。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backends.gpu_colorful import ColorfulGpu  # noqa: E402


def main() -> int:
    with ColorfulGpu() as gpu:
        if not gpu.open() or not gpu.handshake():
            print("初始化失败:", gpu.last_error)
            return 1

        print("A) 写纯红，保持 12 秒…")
        gpu.set_color(255, 0, 0)
        time.sleep(12)

        print("B) 停止一切写入，静置 25 秒（现在开始盯灯）…")
        time.sleep(25)

        print("C) 写纯绿，确认器件还在…")
        gpu.set_color(0, 255, 0)
        time.sleep(3)

        print("\n恢复青色…")
        gpu.set_color(0, 190, 255)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
