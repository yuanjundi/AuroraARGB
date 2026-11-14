"""七彩虹显卡灯控驱动（用户态实现，无需内核驱动）。

通道
----
GPU 自己的 I2C 总线。NVIDIA 通过 NVAPI 暴露了用户态的 I2C 读写接口，因此
不需要装驱动、不需要管理员内核模块。实测这台机器的灯控芯片挂在：

    端口 portId = 1，7 位地址 0x61

协议
----
握手：写入 6 字节 {AA EF 81 02 1C 02}，再读 64 字节，校验头三字节 AA EF 81。

设色（V1，11 字节）：

    AA EF 12 03 01 FF  R  G  B  CRC_L CRC_H

    CRC = 前 9 字节的累加和，低字节在前。

整条灯带是单区单色，所以 11 字节就够。另有一种 122 字节的 V2 包（38 颗灯珠
逐颗设色），只在 RTX 4070 Vulcan 上使用。

协议事实来源
------------
数据包格式来自 OpenRGB 的 ColorfulGPUController（GPL-2.0）实现的公开行为，
此处按协议重新实现，未复制其代码。若要把本项目整体改为 GPL 发布，请注意
这一处的出处标注。
"""
from __future__ import annotations

import ctypes
from typing import Optional, Tuple

NVAPI_DLL = "nvapi64.dll"

ID_INITIALIZE = 0x0150E828
ID_UNLOAD = 0xD22BDD7E
ID_ENUM_PHYSICAL_GPUS = 0xE5AC921F
ID_GPU_GET_FULLNAME = 0xCEEE8E9F
ID_GPU_GET_PCI_ID = 0x2DDFB66E
ID_I2C_READ_EX = 0x4D7B0709
ID_I2C_WRITE_EX = 0x283AC65A

NVAPI_OK = 0
VER3 = 0x00030040            # (3 << 16) | sizeof(NV_I2C_INFO_V3)

I2C_PORT = 1
I2C_ADDR = 0x61

HANDSHAKE = (0xAA, 0xEF, 0x81, 0x02, 0x1C, 0x02)
PACKET_V1_LEN = 11


class NV_I2C_INFO_V3(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("displayMask", ctypes.c_uint32),
        ("bIsDDCPort", ctypes.c_uint8),
        ("i2cDevAddress", ctypes.c_uint8),
        ("pbI2cRegAddress", ctypes.POINTER(ctypes.c_uint8)),
        ("regAddrSize", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_uint8)),
        ("cbSize", ctypes.c_uint32),
        ("i2cSpeed", ctypes.c_uint32),
        ("i2cSpeedKhz", ctypes.c_uint32),
        ("portId", ctypes.c_uint8),
        ("bIsPortIdSet", ctypes.c_uint32),
    ]


def build_packet(r: int, g: int, b: int) -> bytes:
    """构造 V1 设色包（11 字节），含累加和校验。"""
    body = [0xAA, 0xEF, 0x12, 0x03, 0x01, 0xFF,
            r & 0xFF, g & 0xFF, b & 0xFF]
    crc = sum(body) & 0xFFFF
    return bytes(body + [crc & 0xFF, (crc >> 8) & 0xFF])


class ColorfulGpu:
    """一块七彩虹显卡的灯控。用 with 语句或显式 open()/close()。"""

    def __init__(self) -> None:
        self._nvapi = None
        self._handle: Optional[int] = None
        self._read = None
        self._write = None
        self.ready = False
        self.last_error = ""
        self.gpu_name = ""

    # ------------------------------------------------------------ 生命周期

    def open(self) -> bool:
        try:
            self._nvapi = ctypes.WinDLL(NVAPI_DLL)
        except OSError as exc:
            self.last_error = "加载 %s 失败: %s" % (NVAPI_DLL, exc)
            return False

        init = self._fn(ID_INITIALIZE, ctypes.c_int, [])
        if init is None:
            self.last_error = "取不到 NvAPI_Initialize"
            return False
        st = init()
        if st != NVAPI_OK:
            self.last_error = "NvAPI_Initialize 返回 %d" % st
            return False

        enum = self._fn(
            ID_ENUM_PHYSICAL_GPUS, ctypes.c_int,
            [ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32)])
        handles = (ctypes.c_void_p * 64)()
        count = ctypes.c_uint32(0)
        if enum is None or enum(handles, ctypes.byref(count)) != NVAPI_OK or not count.value:
            self.last_error = "找不到物理 GPU"
            return False
        self._handle = handles[0]

        name_fn = self._fn(ID_GPU_GET_FULLNAME, ctypes.c_int,
                           [ctypes.c_void_p, ctypes.c_char_p])
        if name_fn is not None:
            buf = ctypes.create_string_buffer(64)
            if name_fn(self._handle, buf) == NVAPI_OK:
                self.gpu_name = buf.value.decode("mbcs", "replace")

        self._read = self._fn(
            ID_I2C_READ_EX, ctypes.c_int,
            [ctypes.c_void_p, ctypes.POINTER(NV_I2C_INFO_V3),
             ctypes.POINTER(ctypes.c_uint32)])
        self._write = self._fn(
            ID_I2C_WRITE_EX, ctypes.c_int,
            [ctypes.c_void_p, ctypes.POINTER(NV_I2C_INFO_V3),
             ctypes.POINTER(ctypes.c_uint32)])

        if self._read is None or self._write is None:
            self.last_error = "NVAPI 没有暴露 I2C 读写接口"
            return False

        self.ready = True
        return True

    def close(self) -> None:
        if self._nvapi is not None:
            try:
                unload = self._fn(ID_UNLOAD, ctypes.c_int, [])
                if unload is not None:
                    unload()
            except Exception:
                pass
        self._nvapi = None
        self._handle = None
        self.ready = False

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------ I2C 原语

    def _fn(self, fid: int, restype, argtypes):
        q = self._nvapi.nvapi_QueryInterface
        q.argtypes = [ctypes.c_uint32]
        q.restype = ctypes.c_void_p
        ptr = q(fid)
        if not ptr:
            return None
        return ctypes.CFUNCTYPE(restype, *argtypes)(ptr)

    def _info(self, data_ptr, n: int) -> NV_I2C_INFO_V3:
        info = NV_I2C_INFO_V3()
        info.version = VER3
        info.bIsDDCPort = 0
        info.i2cDevAddress = (I2C_ADDR << 1) & 0xFF
        info.pbI2cRegAddress = ctypes.POINTER(ctypes.c_uint8)()
        info.regAddrSize = 0
        info.pbData = data_ptr
        info.cbSize = n
        info.i2cSpeed = 0xFFFF
        info.i2cSpeedKhz = 0
        info.portId = I2C_PORT
        info.bIsPortIdSet = 1
        return info

    def write(self, payload: bytes) -> int:
        """纯 I2C 块写（不带寄存器地址）。返回 NVAPI 状态码。"""
        buf = (ctypes.c_uint8 * len(payload))(*payload)
        info = self._info(buf, len(payload))
        ex = ctypes.c_uint32(0)
        return self._write(self._handle, ctypes.byref(info), ctypes.byref(ex))

    def read(self, n: int = 64) -> Tuple[int, bytes]:
        buf = (ctypes.c_uint8 * n)()
        info = self._info(buf, n)
        ex = ctypes.c_uint32(0)
        st = self._read(self._handle, ctypes.byref(info), ctypes.byref(ex))
        return st, bytes(buf[:n])

    # ------------------------------------------------------------ 业务接口

    def handshake(self) -> bool:
        """写入握手包再读回，确认对端是七彩虹灯控。"""
        st = self.write(bytes(HANDSHAKE))
        if st != NVAPI_OK:
            self.last_error = "握手写入失败，状态 %d" % st
            return False
        st, data = self.read(64)
        if st != NVAPI_OK:
            self.last_error = "握手读取失败，状态 %d" % st
            return False
        if data[:3] != b"\xAA\xEF\x81":
            self.last_error = "握手响应不符: %s" % data[:8].hex(" ")
            return False
        return True

    def set_color(self, r: int, g: int, b: int) -> bool:
        pkt = build_packet(r, g, b)
        st = self.write(pkt)
        if st != NVAPI_OK:
            self.last_error = "设色写入失败，状态 %d" % st
            return False
        return True
