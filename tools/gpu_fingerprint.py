"""GPU I2C 设备指纹 —— 只读寄存器，判断 0x61 到底是灯控还是供电芯片。

判断依据：
  · PMBus 设备（供电/温控）在 0x79 有 PMBUS_REVISION（通常 0x22/0x23），
    0x9A/0x9B 是 MFR_ID / MFR_MODEL 的可读 ASCII 串。
  · RGB 控制器通常没有 PMBus 规范结构，寄存器图是厂商私有的。

全程只调用 I2CReadEx。
"""
from __future__ import annotations

import ctypes
import sys

from gpu_probe import (
    NV_I2C_INFO_V3, VER3, NVAPI_OK,
    ID_INITIALIZE, ID_UNLOAD, ID_ENUM_PHYSICAL_GPUS, ID_GPU_GET_FULLNAME,
    ID_I2C_READ_EX, query,
)

TARGET_ADDR = 0x61


def make_reader(nvapi):
    read_ptr = query(nvapi, ID_I2C_READ_EX)
    read_ex = ctypes.CFUNCTYPE(
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.POINTER(NV_I2C_INFO_V3),
        ctypes.POINTER(ctypes.c_uint32),
    )(read_ptr)

    def read(handle, port: int, addr7: int, reg: int, n: int = 1):
        info = NV_I2C_INFO_V3()
        info.version = VER3
        info.bIsDDCPort = 0
        info.i2cDevAddress = (addr7 << 1) & 0xFF
        regbuf = (ctypes.c_uint8 * 1)(reg)
        info.pbI2cRegAddress = regbuf
        info.regAddrSize = 1
        buf = (ctypes.c_uint8 * max(1, n))()
        info.pbData = buf
        info.cbSize = n
        info.i2cSpeed = 0xFFFF
        info.i2cSpeedKhz = 0
        info.portId = port
        info.bIsPortIdSet = 1
        ex = ctypes.c_uint32(0)
        st = read_ex(handle, ctypes.byref(info), ctypes.byref(ex))
        return st, bytes(buf[:n])

    return read


def main() -> int:
    print("=" * 62)
    print(" 设备指纹 · I2C 地址 0x%02X（只读）" % TARGET_ADDR)
    print("=" * 62)

    nvapi = ctypes.WinDLL("nvapi64.dll")
    ctypes.CFUNCTYPE(ctypes.c_int)(query(nvapi, ID_INITIALIZE))()

    handles = (ctypes.c_void_p * 64)()
    count = ctypes.c_uint32(0)
    ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_void_p),
                     ctypes.POINTER(ctypes.c_uint32))(
        query(nvapi, ID_ENUM_PHYSICAL_GPUS))(handles, ctypes.byref(count))
    h = handles[0]

    read = make_reader(nvapi)

    # --- 1. 全寄存器扫描 0x00-0xFF，看有没有结构 ---
    print("\n[1] 寄存器 0x00-0xFF 逐字节读取")
    dump = {}
    ok_cnt = 0
    for reg in range(0x100):
        st, data = read(h, 1, TARGET_ADDR, reg, 1)
        if st == NVAPI_OK:
            dump[reg] = data[0]
            ok_cnt += 1
    print("    应答寄存器数: %d / 256" % ok_cnt)

    print("\n    非零寄存器（挑着看，避免刷屏）:")
    shown = 0
    for reg in sorted(dump):
        v = dump[reg]
        if v != 0:
            print("      0x%02X = 0x%02X" % (reg, v))
            shown += 1
            if shown >= 48:
                print("      ...（还有更多，略）")
                break
    if shown == 0:
        print("      全是 0x00 —— 可能是写命令型器件，需要先写再读")

    # --- 2. PMBus 特征检查 ---
    print("\n[2] PMBus 特征检查（供电芯片的身份证）")
    st, rev = read(h, 1, TARGET_ADDR, 0x79, 1)
    print("    0x79 PMBUS_REVISION -> 状态=%d 值=%s" % (
        st, ("0x%02X" % rev[0]) if st == NVAPI_OK else "读不到"))
    if st == NVAPI_OK and rev[0] in (0x11, 0x12, 0x22, 0x23, 0x33):
        print("    ⚠ 这是合法 PMBus 版本号 —— 强烈提示它是供电/温控器件！")

    for reg, label in ((0x99, "MFR_ID"), (0x9A, "MFR_MODEL"), (0x9B, "MFR_REVISION")):
        st, data = read(h, 1, TARGET_ADDR, reg, 8)
        if st == NVAPI_OK:
            txt = "".join(chr(c) if 32 <= c < 127 else "." for c in data)
            print("    0x%02X %-12s -> %s" % (reg, label, txt))

    # --- 3. 连续块读，看是不是大片 0xFF（未接/无数据）---
    print("\n[3] 块读 0x00 起 16 字节")
    st, blk = read(h, 1, TARGET_ADDR, 0x00, 16)
    print("    状态=%d 数据=%s" % (st, blk.hex(" ") if st == NVAPI_OK else "-"))

    print("\n完成。没有发生任何写入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
