"""七彩虹（COLORFUL）主板 ARGB 直连后端。

协议来自开源社区对 iGame Center 的逆向结果：64 字节 HID Output 报告、
每包 20 颗灯珠、包尾发送 0xFF 提交帧。本模块不复用厂商驱动，
直接通过 hidapi 写 HID 端点，因此可以完全替代 iGame Center 常驻服务。

    上报头：[0x00, 0x01, 0x00, 0x88, 包序号] + 20 × (R, G, B)
    结束帧：[0x00, 0x01, 0x00, 0x88, 0xFF] + 全 0
"""
from __future__ import annotations

import time
from typing import List, Optional

from . import Backend, Channel

try:  # hidapi 缺失时后端整体禁用，不影响其它功能
    import hid as _hid
except Exception:  # pragma: no cover
    _hid = None


VID = 0x2F4C
PIDS = (0x1020, 0x1018, 0x1017, 0x1013, 0x1006, 0x1000)
LEDS_PER_PACKET = 20
REPORT_LEN = 64          # HID 描述符里 Output Report 为 64×8bit
PACKET_LEN = REPORT_LEN + 1  # hidapi 首字节是 Report ID


class ColorfulBackend(Backend):
    id = "colorful"
    label = "七彩虹主板"
    description = "直接驱动 COLORFUL 主板的 ARGB 控制器，无需 iGame Center"

    def __init__(self, led_count: int = 220) -> None:
        self.led_count = max(1, int(led_count))
        self._dev = None
        self._path: Optional[bytes] = None
        self._name = ""
        self._err = ""
        self._fails = 0
        self._buf = bytearray(PACKET_LEN)
        self._last_push = 0.0

    # ------------------------------------------------------------ 设备发现

    @staticmethod
    def available() -> bool:
        return _hid is not None

    def _find_path(self):
        if _hid is None:
            return None
        try:
            candidates = []
            for pid in PIDS:
                for d in _hid.enumerate(VID, pid):
                    up = d.get("usage_page") or 0
                    us = d.get("usage") or 0
                    itf = d.get("interface_number")
                    if up == 0xFF01 and us == 0x0001:
                        candidates.append(d)
                    elif itf == 1 and up == 0:
                        candidates.append(d)
            if not candidates:
                return None
            return candidates[0]
        except Exception as exc:  # pragma: no cover
            self._err = "枚举失败: %s" % exc
            return None

    def open(self) -> bool:
        if _hid is None:
            self._err = "缺少 hidapi 组件"
            return False
        if self._dev is not None:
            return True
        info = self._find_path()
        if info is None:
            self._err = "未找到七彩虹 ARGB 控制器"
            return False
        try:
            dev = _hid.device()
            dev.open_path(info["path"])
            try:
                dev.set_nonblocking(1)
            except Exception:
                pass
            self._dev = dev
            self._path = info["path"]
            self._name = (info.get("product_string") or "Colorful MBoard")
            self._err = ""
            self._fails = 0
            return True
        except Exception as exc:
            self._err = "打开设备失败: %s" % exc
            self._dev = None
            return False

    def close(self) -> None:
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
        self._dev = None

    @property
    def ready(self) -> bool:
        return self._dev is not None

    @property
    def status_text(self) -> str:
        if self._dev is None:
            return self._err or "未连接"
        return "已连接 %s" % self._name

    # ------------------------------------------------------------ 通道

    def scan(self) -> List[Channel]:
        if not self.open():
            return []
        return [
            Channel(
                key="colorful::mb",
                name="主板 ARGB",
                device_name=self._name or "COLORFUL 主板",
                led_count=self.led_count,
                kind="mb",
                backend_id=self.id,
                note="直连 HID · 含板载灯与 ARGB 排针",
                extra={"pid": self._path},
            )
        ]

    # ------------------------------------------------------------ 写入

    def _write(self, buf: bytearray) -> bool:
        if self._dev is None:
            return False
        try:
            w = self._dev.write(buf)
        except Exception:
            w = 0
        if not w:
            self._fails += 1
            if self._fails >= 6:
                # 连续失败，认为设备被抢占或已拔出，等待上层重连
                self.close()
                self._err = "设备写入失败（可能被 iGame Center 占用）"
            return False
        self._fails = 0
        return True

    def push(self, ch: Channel, data: bytearray) -> bool:
        if self._dev is None and not self.open():
            return False

        n = min(len(data) // 3, self.led_count)
        packets = (self.led_count + LEDS_PER_PACKET - 1) // LEDS_PER_PACKET
        buf = self._buf
        ok = True

        for p in range(packets):
            # 重置数据区，末尾不足一包的灯珠填黑
            for k in range(5, PACKET_LEN):
                buf[k] = 0
            buf[0] = 0x00
            buf[1] = 0x01
            buf[2] = 0x00
            buf[3] = 0x88
            buf[4] = p & 0xFF
            base = p * LEDS_PER_PACKET
            for i in range(LEDS_PER_PACKET):
                li = base + i
                if li >= n:
                    break
                src = li * 3
                off = 5 + i * 3
                buf[off] = data[src]
                buf[off + 1] = data[src + 1]
                buf[off + 2] = data[src + 2]
            if not self._write(buf):
                ok = False
                break

        # 提交帧
        for k in range(5, PACKET_LEN):
            buf[k] = 0
        buf[0] = 0x00
        buf[1] = 0x01
        buf[2] = 0x00
        buf[3] = 0x88
        buf[4] = 0xFF
        if not self._write(buf):
            ok = False
        return ok

    # ------------------------------------------------------------ 厂商服务

    @staticmethod
    def vendor_service_running() -> bool:
        """iGame Center 服务是否在跑（会和本程序抢 HID 设备）。"""
        import subprocess
        try:
            r = subprocess.run(
                ["sc", "query", "iGameCenterService"],
                capture_output=True, timeout=2.0,
                creationflags=0x08000000,
            )
            out = (r.stdout or b"").decode("mbcs", errors="replace")
            return "RUNNING" in out.upper()
        except Exception:
            return False

    @staticmethod
    def stop_vendor_service() -> bool:
        """尝试停止 iGame Center 服务（需要管理员权限）。"""
        import subprocess
        try:
            r = subprocess.run(
                ["net", "stop", "iGameCenterService"],
                capture_output=True, timeout=8.0,
                creationflags=0x08000000,
            )
            return r.returncode == 0
        except Exception:
            return False
