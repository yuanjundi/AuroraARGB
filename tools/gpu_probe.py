"""GPU I2C 只读探针 —— 自己写驱动的第一步。

原理
----
显卡上的 RGB 控制芯片挂在 GPU 自己的 I2C 总线上。NVIDIA 通过 NVAPI 暴露了
一条用户态的 I2C 读写通道（NvAPI_I2CReadEx / NvAPI_I2CWriteEx），OpenRGB
就是用这条通道控制各家显卡灯的。所以「写驱动」不一定需要内核驱动。

⚠ 安全边界
----------
同一条 I2C 总线上还挂着显存供电控制器（VRM）、12VHPWR 检测、PCB 温度传感器。
**写错寄存器可能让供电拉不出电压**。所以这个脚本：

    · 只调用 I2CReadEx，一次都没有调用 I2CWriteEx
    · 每次只读 1 字节，寄存器地址固定 0x00
    · 地址范围限定在 RGB 控制器常见的几段，不是 0x00-0x7F 全扫

用法：以管理员身份运行
    python gpu_probe.py
"""
from __future__ import annotations

import ctypes
import sys

NVAPI_DLL = "nvapi64.dll"

# --- NVAPI 函数 ID（nvapi_QueryInterface 的入参）---------------------------
ID_INITIALIZE = 0x0150E828
ID_UNLOAD = 0xD22BDD7E
ID_ENUM_PHYSICAL_GPUS = 0xE5AC921F
ID_GPU_GET_FULLNAME = 0xCEEE8E9F
ID_GPU_GET_PCI_ID = 0x2DDFB66E
ID_I2C_READ_EX = 0x4D7B0709
ID_I2C_WRITE_EX = 0x283AC65A  # 仅取指针用于确认存在，绝不调用

NVAPI_OK = 0

# NV_I2C_INFO_VER3 = (3 << 16) | sizeof(NV_I2C_INFO_V3)
VER3 = 0x00030040


class NV_I2C_INFO_V3(ctypes.Structure):
    """与 nvapi.h 中的 NV_I2C_INFO_V3 逐字段对齐（64 位下 64 字节）。"""
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


# RGB 控制芯片常见的地址段。没有全扫 0x00-0x7F：
#   0x18-0x1F  部分 LED 驱动
#   0x2E-0x2F  ENE / 类似 Super I/O 风格
#   0x30-0x37  常见 RGB 控制器窗口
#   0x40-0x4F  温感 / 部分 LED
#   0x58-0x5F  EEPROM 段
#   0x60-0x67  RGB 控制器最常见的一段
CANDIDATE_ADDRS = (
    list(range(0x18, 0x20))
    + list(range(0x2E, 0x30))
    + list(range(0x30, 0x38))
    + list(range(0x40, 0x50))
    + list(range(0x58, 0x60))
    + list(range(0x60, 0x68))
)

PORTS = (1, 2, 3, 4)


def query(nvapi, fid: int):
    fn = nvapi.nvapi_QueryInterface
    fn.argtypes = [ctypes.c_uint32]
    fn.restype = ctypes.c_void_p
    return fn(fid)


def main() -> int:
    print("=" * 62)
    print(" GPU I2C 只读探针 · 看看能不能摸到显卡的灯控芯片")
    print("=" * 62)

    size = ctypes.sizeof(NV_I2C_INFO_V3)
    print("NV_I2C_INFO_V3 结构大小: %d 字节 (期望 64)" % size)
    if size != 64:
        print("!! 结构对齐不对，后续调用会返回 INCOMPATIBLE_STRUCT_VERSION")

    try:
        nvapi = ctypes.WinDLL(NVAPI_DLL)
    except OSError as exc:
        print("!! 加载 %s 失败: %s" % (NVAPI_DLL, exc))
        return 1

    init_ptr = query(nvapi, ID_INITIALIZE)
    if not init_ptr:
        print("!! 取不到 NvAPI_Initialize")
        return 1
    init = ctypes.CFUNCTYPE(ctypes.c_int)(init_ptr)
    st = init()
    print("NvAPI_Initialize -> %d %s" % (st, "(OK)" if st == NVAPI_OK else "(失败)"))
    if st != NVAPI_OK:
        return 1

    # --- 枚举物理 GPU ---
    enum_ptr = query(nvapi, ID_ENUM_PHYSICAL_GPUS)
    enum = ctypes.CFUNCTYPE(
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint32),
    )(enum_ptr)
    handles = (ctypes.c_void_p * 64)()
    count = ctypes.c_uint32(0)
    st = enum(handles, ctypes.byref(count))
    print("NvAPI_EnumPhysicalGPUs -> %d, GPU 数量 = %d" % (st, count.value))
    if st != NVAPI_OK or count.value == 0:
        return 1

    name_fn = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_char_p)(
        query(nvapi, ID_GPU_GET_FULLNAME))

    # --- 确认 I2C 接口存在（只取指针，不调用写）---
    read_ptr = query(nvapi, ID_I2C_READ_EX)
    write_ptr = query(nvapi, ID_I2C_WRITE_EX)
    print("NvAPI_I2CReadEx  指针: %s" % ("可用" if read_ptr else "取不到"))
    print("NvAPI_I2CWriteEx 指针: %s （本次不会调用）" % ("存在" if write_ptr else "取不到"))
    if not read_ptr:
        return 1

    read_ex = ctypes.CFUNCTYPE(
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.POINTER(NV_I2C_INFO_V3),
        ctypes.POINTER(ctypes.c_uint32),
    )(read_ptr)

    def i2c_read1(handle, port: int, addr7: int, reg: int = 0):
        """只读 1 字节。返回 (状态码, 字节值)。"""
        info = NV_I2C_INFO_V3()
        info.version = VER3
        info.displayMask = 0
        info.bIsDDCPort = 0
        info.i2cDevAddress = (addr7 << 1) & 0xFF
        regbuf = (ctypes.c_uint8 * 1)(reg)
        info.pbI2cRegAddress = regbuf
        info.regAddrSize = 1
        databuf = (ctypes.c_uint8 * 1)()
        info.pbData = databuf
        info.cbSize = 1
        info.i2cSpeed = 0xFFFF
        info.i2cSpeedKhz = 0
        info.portId = port
        info.bIsPortIdSet = 1
        ex = ctypes.c_uint32(0)
        st = read_ex(handle, ctypes.byref(info), ctypes.byref(ex))
        return st, databuf[0]

    for gi in range(count.value):
        h = handles[gi]
        buf = ctypes.create_string_buffer(64)
        name_fn(h, buf)
        print("\n--- GPU %d: %s ---" % (gi, buf.value.decode("mbcs", "replace")))

        for port in PORTS:
            hits = []
            for addr in CANDIDATE_ADDRS:
                st, val = i2c_read1(h, port, addr)
                if st == NVAPI_OK:
                    hits.append((addr, val))
            if hits:
                print("  端口 %d 上应答的地址：" % port)
                for addr, val in hits:
                    print("    0x%02X  首字节=0x%02X" % (addr, val))
            else:
                print("  端口 %d 无应答" % port)

    unload_ptr = query(nvapi, ID_UNLOAD)
    if unload_ptr:
        ctypes.CFUNCTYPE(ctypes.c_int)(unload_ptr)()

    print("\n完成。全程只用 I2CReadEx，没有发生任何写入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
