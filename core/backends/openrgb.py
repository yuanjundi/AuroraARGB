"""OpenRGB SDK 后端（TCP 6742）。

用于覆盖主板直连管不到的设备：显卡 ARGB、内存条灯条、灯带控制器等。
协议实现参考 OpenRGB NetworkProtocol（ORGB 包头 + 小端整数）。
"""
from __future__ import annotations

import os
import socket
import struct
import subprocess
from typing import Dict, List, Optional, Tuple

from . import Backend, Channel

ORGB_MAGIC = b"ORGB"

PKT_REQUEST_CONTROLLER_COUNT = 0
PKT_REQUEST_CONTROLLER_DATA = 1
PKT_REQUEST_PROTOCOL_VERSION = 40
PKT_SET_CLIENT_NAME = 50
PKT_SET_CUSTOM_MODE = 1100
PKT_UPDATE_LEDS = 1050

MODE_FLAG_HAS_PER_LED_COLOR = 1 << 2

DEVICE_TYPE = {
    0: ("mb", "主板"),
    1: ("ram", "内存"),
    2: ("gpu", "显卡"),
    3: ("cooler", "散热器"),
    4: ("strip", "灯带"),
    5: ("keyboard", "键盘"),
    6: ("mouse", "鼠标"),
    7: ("kbd", "键盘"),
    8: ("headset", "耳机"),
}


class _Reader:
    __slots__ = ("d", "o")

    def __init__(self, data: bytes) -> None:
        self.d = data
        self.o = 0

    def u16(self) -> int:
        v = struct.unpack_from("<H", self.d, self.o)[0]
        self.o += 2
        return v

    def u32(self) -> int:
        v = struct.unpack_from("<I", self.d, self.o)[0]
        self.o += 4
        return v

    def string(self) -> str:
        n = self.u16()
        v = self.d[self.o:self.o + n].decode("utf-8", "replace")
        self.o += n
        return v

    def eof(self) -> bool:
        return self.o >= len(self.d)


class _Device:
    __slots__ = ("index", "name", "dev_type", "leds", "modes", "active", "custom")

    def __init__(self) -> None:
        self.index = 0
        self.name = ""
        self.dev_type = 0
        self.leds = 0
        self.modes: List[Tuple[str, int, int]] = []   # (name, flags, color_mode)
        self.active = 0
        self.custom = 0


def _parse_device(data: bytes) -> Optional[_Device]:
    try:
        r = _Reader(data)
        r.u32()               # data_size
        d = _Device()
        d.dev_type = r.u32()
        d.name = r.string()
        r.string()            # vendor
        r.string()            # description
        r.string()            # version
        r.string()            # serial
        r.string()            # location

        n_modes = r.u16()
        for _ in range(n_modes):
            mname = r.string()
            _value = r.u32()
            flags = r.u32()
            r.u32()           # speed_min
            r.u32()           # speed_max
            r.u32()           # brightness_min
            r.u32()           # brightness_max
            r.u32()           # per_led_color_min
            r.u32()           # per_led_color_max
            r.u32()           # mode_flags
            color_mode = r.u32()
            n_colors = r.u16()
            r.o += n_colors * 4
            d.modes.append((mname, flags, color_mode))
        d.active = r.u32()

        n_zones = r.u16()
        for _ in range(n_zones):
            r.string()        # zone name
            r.u32()           # zone type
            r.u32()           # leds_min
            r.u32()           # leds_max
            r.u32()           # leds_count
            msize = r.u16()
            r.o += msize * 8

        n_leds = r.u16()
        for _ in range(n_leds):
            r.string()
            r.u32()
        d.leds = n_leds
        return d
    except Exception:
        return None


class OpenRGBBackend(Backend):
    id = "openrgb"
    label = "OpenRGB"
    description = "通过 OpenRGB SDK 统一控制显卡、内存、灯带等设备"

    def __init__(self, host: str = "127.0.0.1", port: int = 6742) -> None:
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None
        self._proto = 3
        self._devices: List[_Device] = []
        self._err = ""
        self._frames = 0

    # ------------------------------------------------------------ 连接

    @property
    def ready(self) -> bool:
        return self._sock is not None

    @property
    def status_text(self) -> str:
        if self._sock is None:
            return self._err or "未启动"
        return "已连接 %d 台设备" % len(self._devices)

    def _send(self, dev_idx: int, pkt: int, data: bytes = b"") -> None:
        assert self._sock is not None
        self._sock.sendall(ORGB_MAGIC + struct.pack("<III", dev_idx, pkt, len(data)) + data)

    def _recv_exact(self, n: int) -> bytes:
        assert self._sock is not None
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("连接被关闭")
            buf += chunk
        return buf

    def _recv(self) -> Tuple[int, int, bytes]:
        hdr = self._recv_exact(16)
        if hdr[:4] != ORGB_MAGIC:
            raise ConnectionError("协议不匹配")
        dev_idx, pkt, size = struct.unpack("<III", hdr[4:16])
        data = self._recv_exact(size) if size else b""
        return dev_idx, pkt, data

    def connect(self) -> bool:
        if self._sock is not None:
            return True
        try:
            s = socket.create_connection((self.host, self.port), timeout=1.2)
            s.settimeout(1.5)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock = s
            self._send(0, PKT_REQUEST_PROTOCOL_VERSION)
            _, _, data = self._recv()
            if len(data) >= 4:
                self._proto = struct.unpack_from("<I", data, 0)[0]
            self._send(0, PKT_SET_CLIENT_NAME, b"Aurora ARGB")
            self._err = ""
            return True
        except Exception as exc:
            self._err = "无法连接 OpenRGB（%s）" % exc
            self.close()
            return False

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None

    # ------------------------------------------------------------ 扫描

    def scan(self) -> List[Channel]:
        if not self.connect():
            return []
        out: List[Channel] = []
        try:
            self._send(0, PKT_REQUEST_CONTROLLER_COUNT)
            _, _, data = self._recv()
            count = struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else 0
            count = max(0, min(count, 64))

            self._devices = []
            for i in range(count):
                self._send(i, PKT_REQUEST_CONTROLLER_DATA, struct.pack("<I", self._proto))
                _, _, ddata = self._recv()
                dev = _parse_device(ddata)
                if dev is None or dev.leds <= 0:
                    continue
                dev.index = i
                # 选 Direct / Custom 模式
                best = None
                for mi, (mname, flags, _cm) in enumerate(dev.modes):
                    low = mname.lower()
                    if "direct" in low or "custom" in low:
                        best = mi
                        break
                if best is None:
                    for mi, (mname, flags, _cm) in enumerate(dev.modes):
                        if flags & MODE_FLAG_HAS_PER_LED_COLOR:
                            best = mi
                            break
                if best is None:
                    best = dev.active if dev.modes else 0
                dev.custom = best
                self._devices.append(dev)

                try:
                    self._send(i, PKT_SET_CUSTOM_MODE, struct.pack("<I", best))
                except Exception:
                    pass

                kind, label = DEVICE_TYPE.get(dev.dev_type, ("strip", "设备"))
                out.append(
                    Channel(
                        key="openrgb::%d" % i,
                        name="%s" % (dev.name or label),
                        device_name=dev.name or label,
                        led_count=dev.leds,
                        kind=kind,
                        backend_id=self.id,
                        note="OpenRGB · %s" % label,
                        native_index=i,
                    )
                )
            return out
        except Exception as exc:
            self._err = "读取设备失败: %s" % exc
            self.close()
            return []

    # ------------------------------------------------------------ 写入

    def push(self, ch: Channel, data: bytearray) -> bool:
        if self._sock is None and not self.connect():
            return False
        dev = None
        for d in self._devices:
            if d.index == ch.native_index:
                dev = d
                break
        if dev is None:
            return False
        n = min(dev.leds, len(data) // 3)
        payload = bytes(data[: n * 3])
        if n < dev.leds:
            payload += bytes((dev.leds - n) * 3)
        try:
            self._send(dev.index, PKT_UPDATE_LEDS, payload)
            self._frames += 1
            return True
        except Exception:
            self.close()
            return False

    # ------------------------------------------------------------ 辅助

    @staticmethod
    def find_executable() -> Optional[str]:
        cands = [
            r"C:\Program Files\OpenRGB\OpenRGB.exe",
            r"C:\Program Files (x86)\OpenRGB\OpenRGB.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\OpenRGB\OpenRGB.exe"),
            os.path.expandvars(r"%USERPROFILE%\Downloads\OpenRGB\OpenRGB.exe"),
        ]
        for c in cands:
            if os.path.isfile(c):
                return c
        return None

    @staticmethod
    def launch_with_server() -> bool:
        exe = OpenRGBBackend.find_executable()
        if not exe:
            return False
        try:
            subprocess.Popen([exe, "--server", "--startminimized", "--profile", ""],
                             creationflags=0x08000000)
            return True
        except Exception:
            return False
