"""GPU I2C 总线扫描（只读）—— 画一张总线上有哪些设备的地图。

排除保留地址段，避免踩到 I2C 规范里的特殊地址：
    0x00-0x07  通用呼叫 / CBUS / 保留
    0x78-0x7F  10 位地址前缀 / 保留
只做单字节读，寄存器固定 0x00。
"""
from __future__ import annotations

import ctypes
import sys

from gpu_probe import (
    NV_I2C_INFO_V3, VER3, NVAPI_OK,
    ID_INITIALIZE, ID_ENUM_PHYSICAL_GPUS, ID_I2C_READ_EX, query,
)

ADDRS = list(range(0x08, 0x78))
PORTS = list(range(0, 11))


def main() -> int:
    print("=" * 62)
    print(" GPU I2C 总线扫描（只读）")
    print("=" * 62)

    nvapi = ctypes.WinDLL("nvapi64.dll")
    ctypes.CFUNCTYPE(ctypes.c_int)(query(nvapi, ID_INITIALIZE))()

    handles = (ctypes.c_void_p * 64)()
    count = ctypes.c_uint32(0)
    ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_void_p),
                     ctypes.POINTER(ctypes.c_uint32))(
        query(nvapi, ID_ENUM_PHYSICAL_GPUS))(handles, ctypes.byref(count))
    h = handles[0]

    read_ex = ctypes.CFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p,
        ctypes.POINTER(NV_I2C_INFO_V3), ctypes.POINTER(ctypes.c_uint32),
    )(query(nvapi, ID_I2C_READ_EX))

    def read1(port: int, addr7: int) -> int:
        info = NV_I2C_INFO_V3()
        info.version = VER3
        info.bIsDDCPort = 0
        info.i2cDevAddress = (addr7 << 1) & 0xFF
        regbuf = (ctypes.c_uint8 * 1)(0x00)
        info.pbI2cRegAddress = regbuf
        info.regAddrSize = 1
        buf = (ctypes.c_uint8 * 1)()
        info.pbData = buf
        info.cbSize = 1
        info.i2cSpeed = 0xFFFF
        info.i2cSpeedKhz = 0
        info.portId = port
        info.bIsPortIdSet = 1
        ex = ctypes.c_uint32(0)
        return read_ex(h, ctypes.byref(info), ctypes.byref(ex))

    total = 0
    for port in PORTS:
        hits = []
        for addr in ADDRS:
            if read1(port, addr) == NVAPI_OK:
                hits.append(addr)
        if hits:
            total += len(hits)
            print("端口 %-2d : %d 个应答 -> %s" % (
                port, len(hits), ", ".join("0x%02X" % a for a in hits)))
        else:
            print("端口 %-2d : 无" % port)

    print("\n合计应答设备地址数: %d" % total)
    print("说明：只读了 1 字节，没写过任何寄存器。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
