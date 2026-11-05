"""后端基础设施：统一的通道抽象。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Channel:
    """一个可独立控制的灯带/设备。"""

    key: str                 # 全局唯一，形如 "colorful::mb"
    name: str                # 显示名，如 "主板 ARGB"
    device_name: str         # 硬件名，如 "COLORFUL CVN B850I"
    led_count: int
    kind: str = "mb"         # mb / gpu / ram / strip / sync
    backend_id: str = ""
    controllable: bool = True
    note: str = ""
    native_index: int = 0
    extra: Dict[str, object] = field(default_factory=dict)

    @property
    def short(self) -> str:
        return "%s · %d 灯" % (self.name, self.led_count)


class Backend:
    """后端基类。"""

    id: str = "base"
    label: str = "未知"
    description: str = ""

    def scan(self) -> List[Channel]:
        return []

    def push(self, ch: Channel, data: bytearray) -> bool:
        return False

    def close(self) -> None:
        pass

    @property
    def ready(self) -> bool:
        return False

    @property
    def status_text(self) -> str:
        return ""
