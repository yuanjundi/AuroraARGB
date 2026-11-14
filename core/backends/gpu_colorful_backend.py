"""七彩虹显卡灯控后端 —— 把 GPU 灯带变成和主板一样的可编程通道。

和 `colorful.py`（主板 HID）不同，显卡这条走 GPU 自己的 I2C 总线，
通过 NVAPI 的用户态接口访问，不占 HID、不需要内核驱动。

一个限制：显卡灯带物理上是多颗灯珠，但固件只开放「整条同色」写入口
（逐颗寻址已穷举验证不可用，详见 `gpu_colorful.py` 顶部说明），
所以通道里只取第一颗灯珠的颜色下发。亮度由 11 字节包里的亮度字节承载。
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple

from . import Backend, Channel
from .gpu_colorful import ColorfulGpu

# 颜色没变时不重复写；超过这个秒数补写一次，防止控制器自己复位
KEEPALIVE_S = 4.0
# 连续写入的最小间隔，避免把 I2C 总线刷爆
MIN_INTERVAL_S = 0.05


class ColorfulGpuBackend(Backend):
    id = "colorful_gpu"
    label = "七彩虹显卡"
    description = "通过 NVAPI I2C 直连显卡灯控芯片，无需 iGame Center"

    def __init__(self) -> None:
        self._drv = ColorfulGpu()
        self._err = ""
        self._name = ""
        self._last_rgb: Optional[Tuple[int, int, int]] = None
        self._last_at = 0.0
        self._writes = 0

    # ------------------------------------------------------------ 连接

    def open(self) -> bool:
        if self._drv.ready:
            return True
        if not self._drv.open():
            self._err = self._drv.last_error or "NVAPI 初始化失败"
            return False
        if not self._drv.handshake():
            self._err = self._drv.last_error or "灯控握手失败"
            self._drv.close()
            return False
        self._name = self._drv.gpu_name
        self._err = ""
        return True

    def close(self) -> None:
        try:
            self._drv.close()
        except Exception:
            pass

    @property
    def ready(self) -> bool:
        return self._drv.ready

    @property
    def status_text(self) -> str:
        if not self._drv.ready:
            return self._err or "未连接"
        return "%s · I2C 0x61 · 已写 %d 次" % (self._name or "NVIDIA GPU", self._writes)

    # ------------------------------------------------------------ 通道

    def scan(self) -> List[Channel]:
        if not self.open():
            return []
        return [
            Channel(
                key="colorful::gpu",
                name="显卡灯带",
                device_name=self._name or "COLORFUL 显卡",
                led_count=1,
                kind="gpu",
                backend_id=self.id,
                note="NVAPI I2C · 整条同色",
                extra={"addr": "0x61", "port": 1},
            )
        ]

    # ------------------------------------------------------------ 写入

    def push(self, ch: Channel, data: bytearray) -> bool:
        if len(data) < 3:
            return False
        if not self._drv.ready and not self.open():
            return False

        rgb = (data[0], data[1], data[2])
        now = time.monotonic()

        # 颜色没变就不重复下发；闲置太久补写一次
        if rgb == self._last_rgb:
            if now - self._last_at < KEEPALIVE_S:
                return True
        elif now - self._last_at < MIN_INTERVAL_S:
            return True

        ok = self._drv.set_color(*rgb)
        if ok:
            self._last_rgb = rgb
            self._last_at = now
            self._writes += 1
        else:
            self._err = self._drv.last_error or "写入失败"
        return ok
