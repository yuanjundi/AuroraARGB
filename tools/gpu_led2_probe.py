"""探测 iGame Center 里那两条 LED 通道（逆向结论验证）。

从 `iGameAPI.NVAPI.dll` 反汇编得到的线索：

    ReadFromLED : 地址 0x50 / 端口 3 / 读 27 字节
                  报文 = [?, 灯珠数, ?, ?, ?, RGB×7]
    LED2 探测   : 地址 0x58 / 端口 4 / 读 6 字节
                  校验 sum(b0..b3) == b4 | b5<<8
                  首两字节 0x66/0x77/0x88/0x99 表示卡型

本工具只读，不写任何东西。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.backends.gpu_colorful import ColorfulGpu  # noqa: E402

TARGETS = [
    (1, 0x50, 27, None, "ReadFromLED（RGB 回显）"),
    (1, 0x58, 6, 1, "LED2 型号探测（寄存器 1）"),
    (1, 0x58, 6, None, "LED2 型号探测（无寄存器，对照）"),
    (1, 0x61, 64, None, "已知灯控 0x61（对照）"),
]


def main() -> int:
    with ColorfulGpu() as gpu:
        if not gpu.open():
            print("NVAPI 初始化失败:", gpu.last_error)
            return 1
        print("显卡:", gpu.gpu_name)
        print()

        for port, addr, n, reg, tag in TARGETS:
            g = ColorfulGpu(port=port, addr=addr)
            g.open()
            st, data = g.read(n, reg)
            g.close()
            ok = st == 0
            body = data[:n]
            print("=== %s  端口 %d / 地址 0x%02X / %d 字节 ===" % (tag, port, addr, n))
            print("  状态: %s" % ("OK" if ok else "失败(%d)" % st))
            print("  数据: %s" % body.hex(" "))
            if ok and n == 27 and len(body) >= 6:
                print("  → 灯珠数字节 = %d" % body[1])
                for i in range(7):
                    o = 5 + i * 3
                    if o + 2 < n:
                        print("    区域%d RGB = (%3d,%3d,%3d)" % (i + 1, body[o], body[o + 1], body[o + 2]))
            if ok and n == 6 and len(body) >= 6:
                s = body[0] + body[1] + body[2] + body[3]
                t = body[4] | (body[5] << 8)
                print("  → 校验 %d vs %d：%s" % (s, t, "通过" if s == t else "不通过"))
                print("  → 型号 0x%02X%02X" % (body[1], body[0]))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
