"""渲染引擎。

设计要点（为了"低占用"）：
1. 纯计算，不依赖 Qt；由 UI 的定时器驱动，避免多线程竞争。
2. 每个通道复用一个 bytearray，效果函数原地填充，几乎不产生垃圾。
3. 亮度用 256 项查找表，避免逐字节乘法。
4. 设备写入交给单独的写线程，UI 线程永不阻塞在 HID / Socket 上。
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import colors as C
from .backends import Backend, Channel
from .effects import EFFECT_MAP, EffectSpec, default_params, reset_states

RGB = Tuple[int, int, int]


# ---------------------------------------------------------------- 亮度表

class _BrightLUT:
    """按亮度档位缓存 256 项乘法表。"""

    def __init__(self) -> None:
        self._k = -1.0
        self._tbl = list(range(256))

    def get(self, k: float) -> List[int]:
        if abs(k - self._k) < 0.004:
            return self._tbl
        self._k = k
        self._tbl = [min(255, int(i * k + 0.5)) for i in range(256)]
        return self._tbl


_LUT = _BrightLUT()


# ---------------------------------------------------------------- 写入线程

class PushWorker(threading.Thread):
    """把帧推给硬件。队列只保留最新帧，宁可丢帧也不堆积延迟。"""

    def __init__(self) -> None:
        super().__init__(daemon=True, name="argb-writer")
        self.q: "queue.Queue" = queue.Queue(maxsize=8)
        self.running = True
        self.sent = 0
        self.errors = 0
        self.last_ms = 0.0
        self.last_error = ""

    def submit(self, backend: Backend, ch: Channel, data: bytes) -> None:
        item = (backend, ch, data)
        try:
            self.q.put_nowait(item)
        except queue.Full:
            try:
                self.q.get_nowait()
            except queue.Empty:
                pass
            try:
                self.q.put_nowait(item)
            except queue.Full:
                pass

    def run(self) -> None:
        while self.running:
            try:
                backend, ch, data = self.q.get(timeout=0.25)
            except queue.Empty:
                continue
            t0 = time.perf_counter()
            try:
                ok = backend.push(ch, bytearray(data))
                if ok:
                    self.sent += 1
                else:
                    self.errors += 1
                    self.last_error = getattr(backend, "status_text", "")
            except Exception as exc:
                self.errors += 1
                self.last_error = str(exc)
            self.last_ms = (time.perf_counter() - t0) * 1000.0

    def stop(self) -> None:
        self.running = False


# ---------------------------------------------------------------- 通道状态

@dataclass
class ChannelState:
    channel: Channel
    backend: Backend
    enabled: bool = True
    buf: bytearray = field(default_factory=bytearray)
    dirty: bool = True
    last_ok: bool = True
    fps: float = 0.0
    _frames: int = 0
    _acc: float = 0.0


# ---------------------------------------------------------------- 引擎

class Engine:
    def __init__(self) -> None:
        self.writer = PushWorker()
        self.writer.start()

        self.effect_id: str = "rainbow"
        self.params: dict = default_params()
        self.brightness: float = 0.75
        self.paused: bool = False
        self.load: float = 0.0
        self.temp: Optional[float] = None

        self.states: Dict[str, ChannelState] = {}
        self.t: float = 0.0
        self._st: float = 0.0
        self._fps_acc = 0.0
        self._fps_frames = 0
        self.fps: float = 0.0
        self.render_ms: float = 0.0

    # ------------------------------------------------------------ 通道管理

    def register(self, channel: Channel, backend: Backend) -> None:
        if channel.key in self.states:
            self.states[channel.key].channel = channel
            self.states[channel.key].backend = backend
            return
        self.states[channel.key] = ChannelState(channel=channel, backend=backend)

    def unregister_missing(self, alive_keys: set) -> None:
        for k in list(self.states.keys()):
            if k not in alive_keys:
                del self.states[k]

    def clear(self) -> None:
        self.states.clear()
        reset_states()

    @property
    def channels(self) -> List[Channel]:
        return [s.channel for s in self.states.values()]

    # ------------------------------------------------------------ 配置

    def set_effect(self, effect_id: str) -> None:
        if effect_id == self.effect_id:
            return
        spec = EFFECT_MAP.get(effect_id)
        if spec is None:
            return
        self.effect_id = effect_id
        self.params["speed"] = max(0.2, min(4.0, spec.speed))
        self.params["size"] = spec.size
        reset_states()
        self._st = 0.0
        for s in self.states.values():
            s.dirty = True

    def set_color(self, slot: str, rgb: RGB) -> None:
        self.params[slot] = rgb
        for s in self.states.values():
            s.dirty = True

    def set_param(self, key: str, value) -> None:
        self.params[key] = value
        for s in self.states.values():
            s.dirty = True

    def set_brightness(self, b: float) -> None:
        self.brightness = max(0.0, min(1.0, b))
        for s in self.states.values():
            s.dirty = True

    # ------------------------------------------------------------ 每帧

    def tick(self, dt: float) -> Dict[str, bytearray]:
        """推进一帧，返回 {channel_key: rgb_bytes} 供预览使用。"""
        if dt <= 0:
            return {}
        dt = min(dt, 0.2)   # 掉帧时不要一次跳太远
        self._fps_acc += dt
        self._fps_frames += 1
        if self._fps_acc >= 0.5:
            self.fps = self._fps_frames / self._fps_acc
            self._fps_acc = 0.0
            self._fps_frames = 0
        if self.paused:
            return {}

        t0 = time.perf_counter()
        self.t += dt
        spec = EFFECT_MAP.get(self.effect_id) or EFFECT_MAP["rainbow"]
        speed = float(self.params.get("speed", 1.0))
        direction = 1.0 if self.params.get("dir", 1) >= 0 else -1.0
        self._st += dt * speed * direction
        st = self._st

        p = self.params
        p["load"] = self.load
        p["temp"] = self.temp
        lut = _LUT.get(self.brightness) if self.brightness < 0.999 else None

        frame: Dict[str, bytearray] = {}
        staticish = spec.id == "static"

        for key, state in self.states.items():
            if not state.enabled:
                continue
            n = state.channel.led_count
            if len(state.buf) != n * 3:
                state.buf = bytearray(n * 3)
                state.dirty = True
            if staticish and not state.dirty:
                frame[key] = state.buf
                continue
            try:
                spec.fn(self.t, st, n, p, state.buf)
            except Exception:
                # 效果出错时退化为静态色，绝不让 UI 崩
                r, g, b = p.get("c1", (255, 255, 255))
                buf = state.buf
                for i in range(n):
                    buf[i * 3] = r
                    buf[i * 3 + 1] = g
                    buf[i * 3 + 2] = b
            if lut is not None:
                buf = state.buf
                for i in range(len(buf)):
                    buf[i] = lut[buf[i]]
            if not self.paused:
                self.writer.submit(state.backend, state.channel, bytes(state.buf))
            state.dirty = False
            state._frames += 1
            frame[key] = state.buf

        self.render_ms = (time.perf_counter() - t0) * 1000.0
        return frame

    def shutdown(self) -> None:
        self.writer.stop()


# ---------------------------------------------------------------- 工具

def preview_colors(buf: bytearray, count: int) -> List[RGB]:
    """把任意长度的灯带重采样成 count 个颜色，用于界面预览。"""
    if not buf:
        return [(0, 0, 0)] * count
    n = len(buf) // 3
    out: List[RGB] = []
    for i in range(count):
        src = int(i / max(1, count - 1) * (n - 1)) if n > 1 else 0
        src = max(0, min(n - 1, src))
        j = src * 3
        out.append((buf[j], buf[j + 1], buf[j + 2]))
    return out
