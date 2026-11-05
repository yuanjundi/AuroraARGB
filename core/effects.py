"""灯效引擎：所有灯效都是纯函数 ``fn(t, st, n, p, out)``。

* ``t``   —— 真实经过秒数（用于随机/闪烁类效果）
* ``st``  —— 已乘以速度与方向的"效果时间"，绝大多数效果只用它
* ``n``   —— 灯珠数量
* ``p``   —— 参数字典：c1 / c2 / pal / speed / dir / size / load
* ``out`` —— 长度为 ``n * 3`` 的 bytearray，直接原地填充 RGB

引擎在上层统一叠加总亮度，效果本身不处理亮度，避免重复乘法。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from . import colors as C

RGB = Tuple[int, int, int]

# ---------------------------------------------------------------- 预计算表

# 色相查找表，避免每帧对每颗灯调用 hsv_to_rgb
_HUE_LUT: List[RGB] = [C.hsv_to_rgb(i / 512.0, 1.0, 1.0) for i in range(512)]

# 调色板查找表缓存
_PAL_LUT: Dict[str, List[RGB]] = {}


def pal_lut(name: str) -> List[RGB]:
    lut = _PAL_LUT.get(name)
    if lut is None:
        lut = [C.palette_color(name, i / 512.0) for i in range(512)]
        _PAL_LUT[name] = lut
    return lut


def hue(h: float) -> RGB:
    """h 为 0..1，返回饱和满亮度颜色。"""
    return _HUE_LUT[int(h * 512.0) & 511]


def pal(name: str, pos: float) -> RGB:
    return pal_lut(name)[int(pos * 512.0) & 511]


# ---------------------------------------------------------------- 效果状态

_STATE: Dict[str, dict] = {}
_RNG = random.Random(9271)


def _state(key: str, n: int, init: Optional[Callable[[dict], None]] = None) -> dict:
    s = _STATE.get(key)
    if s is None or s.get("_n") != n:
        s = {"_n": n, "_t": 0.0}
        if init:
            init(s)
        _STATE[key] = s
    return s


def reset_states() -> None:
    _STATE.clear()


# ---------------------------------------------------------------- 效果实现

def _fx_static(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    r, g, b = p["c1"]
    for i in range(n):
        j = i * 3
        out[j] = r
        out[j + 1] = g
        out[j + 2] = b


def _fx_breathing(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    k = 0.06 + 0.94 * (0.5 - 0.5 * math.cos(st * 1.9))
    r, g, b = p["c1"]
    r = int(r * k)
    g = int(g * k)
    b = int(b * k)
    for i in range(n):
        j = i * 3
        out[j] = r
        out[j + 1] = g
        out[j + 2] = b


def _fx_rainbow_multi(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    """彩虹全铺 + 整体流动。亮色环绕视觉最讨喜。"""
    off = st * 0.14
    for i in range(n):
        r, g, b = _HUE_LUT[int((i / n + off) * 512.0) & 511]
        j = i * 3
        out[j] = r
        out[j + 1] = g
        out[j + 2] = b


def _fx_rainbow_breath(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    k = 0.10 + 0.90 * (0.5 - 0.5 * math.cos(st * 1.5))
    off = st * 0.10
    for i in range(n):
        r, g, b = _HUE_LUT[int((i / n + off) * 512.0) & 511]
        j = i * 3
        out[j] = int(r * k)
        out[j + 1] = int(g * k)
        out[j + 2] = int(b * k)


def _fx_chase(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    size = max(0.03, p["size"])
    tail = max(0.04, size * 0.55)
    head = (st * 0.35) % 1.0
    lut = pal_lut(p["pal"])
    for i in range(n):
        pos = i / n
        d = (head - pos) % 1.0
        if d < tail:
            k = 1.0 - d / tail
            k = k * k
            r, g, b = lut[int(pos * 512.0) & 511]
            out[i * 3] = int(r * k)
            out[i * 3 + 1] = int(g * k)
            out[i * 3 + 2] = int(b * k)
        else:
            out[i * 3] = 0
            out[i * 3 + 1] = 0
            out[i * 3 + 2] = 0


def _fx_comet(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    size = max(0.05, p["size"])
    head = (st * 0.32) % 1.0
    c = p["c1"]
    bg = p["c2"]
    for i in range(n):
        pos = i / n
        d = (head - pos) % 1.0
        k = math.exp(-(d * d) / (2.0 * size * size * 0.10))
        k2 = math.exp(-(d * d) / (2.0 * size * size * 0.60)) * 0.35
        k = min(1.0, k + k2)
        r = int(bg[0] + (c[0] - bg[0]) * k)
        g = int(bg[1] + (c[1] - bg[1]) * k)
        b = int(bg[2] + (c[2] - bg[2]) * k)
        out[i * 3] = r
        out[i * 3 + 1] = g
        out[i * 3 + 2] = b


def _fx_gradient(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    c1, c2 = p["c1"], p["c2"]
    off = (st * 0.12) % 1.0
    for i in range(n):
        pos = (i / n + off) % 1.0
        k = 0.5 - 0.5 * math.cos(pos * math.tau)
        out[i * 3] = int(c1[0] + (c2[0] - c1[0]) * k)
        out[i * 3 + 1] = int(c1[1] + (c2[1] - c1[1]) * k)
        out[i * 3 + 2] = int(c1[2] + (c2[2] - c1[2]) * k)


def _fx_color_cycle(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    r, g, b = hue(st * 0.08)
    for i in range(n):
        j = i * 3
        out[j] = r
        out[j + 1] = g
        out[j + 2] = b


def _fx_twinkle(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    """每个灯有独立的闪烁相位，靠整数散列保证确定性。"""
    lut = pal_lut(p["pal"])
    for i in range(n):
        h = (i * 2654435761) & 0xFFFFFFFF
        phase = (h % 1000) / 1000.0
        speed = 0.5 + ((h >> 10) % 100) / 120.0
        x = (st * speed * 0.5 + phase) % 1.0
        if x < 0.5:
            k = math.sin(x * math.pi) ** 3
        else:
            k = 0.0
        r, g, b = lut[int(phase * 512.0) & 511]
        out[i * 3] = int(r * k)
        out[i * 3 + 1] = int(g * k)
        out[i * 3 + 2] = int(b * k)


def _fx_fire(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    """整条灯带上随机窜动的火苗，靠热扩散保证连贯。"""

    def init(s):
        s["heat"] = [_RNG.random() * 0.55 for _ in range(max(1, n))]

    s = _state("fire", n, init)
    heat = s["heat"]
    cool = 0.05 + 0.075 * (1.0 - min(1.0, p["size"]))
    for i in range(n):
        heat[i] = max(0.0, heat[i] - cool * (0.45 + 0.7 * _RNG.random()))

    # 邻域扩散，让相邻灯珠的火苗看起来连成一片
    prev = heat[0]
    last = heat[n - 1] if n > 1 else heat[0]
    for i in range(n):
        cur = heat[i]
        nxt = heat[i + 1] if i + 1 < n else last
        heat[i] = cur * 0.66 + (prev + nxt) * 0.17
        prev = cur

    # 全条随机点火
    sparks = max(1, n // 9)
    for _ in range(sparks):
        idx = _RNG.randrange(n)
        heat[idx] = min(1.0, heat[idx] + 0.5 + _RNG.random() * 0.5)

    for i in range(n):
        h = heat[i]
        if h <= 0.02:
            out[i * 3] = 0
            out[i * 3 + 1] = 0
            out[i * 3 + 2] = 0
            continue
        h = min(1.0, h)
        if h < 0.3:
            r, g, b = int(h / 0.3 * 190), 0, 0
        elif h < 0.6:
            k = (h - 0.3) / 0.3
            r, g, b = int(190 + k * 65), int(k * 120), 0
        elif h < 0.85:
            k = (h - 0.6) / 0.25
            r, g, b = 255, int(120 + k * 110), int(k * 40)
        else:
            k = (h - 0.85) / 0.15
            r, g, b = 255, int(230 + k * 25), int(40 + k * 180)
        out[i * 3] = r
        out[i * 3 + 1] = g
        out[i * 3 + 2] = b


def _fx_ripple(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    """从中心周期性扩散的圆环（灯带按圆环看）。"""
    size = max(0.05, p["size"])
    base = p["c2"]
    c = p["c1"]
    period = 2.2
    cycles = max(1, int(n / 24))
    for i in range(n):
        pos = i / n
        # 处理环形距离
        d = abs(pos - 0.5) * 2.0
        val = 0.0
        for cidx in range(cycles):
            ph = ((st * 0.5 + cidx / cycles) % 1.0)
            val = max(val, math.exp(-((d - ph) ** 2) / (2.0 * size * size * 0.08)))
        r = int(base[0] + (c[0] - base[0]) * val)
        g = int(base[1] + (c[1] - base[1]) * val)
        b = int(base[2] + (c[2] - base[2]) * val)
        out[i * 3] = r
        out[i * 3 + 1] = g
        out[i * 3 + 2] = b


def _fx_scanner(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    """来回扫描的 KITT 光条。"""
    size = max(0.04, p["size"] * 0.5)
    x = 0.5 - 0.5 * math.cos(st * 0.9)
    c = p["c1"]
    bg = p["c2"]
    for i in range(n):
        pos = i / n
        k = math.exp(-((pos - x) ** 2) / (2.0 * size * size * 0.25))
        out[i * 3] = int(bg[0] + (c[0] - bg[0]) * k)
        out[i * 3 + 1] = int(bg[1] + (c[1] - bg[1]) * k)
        out[i * 3 + 2] = int(bg[2] + (c[2] - bg[2]) * k)


def _fx_lightning(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    def init(s):
        s["next"] = 1.0
        s["flash"] = 0.0
        s["seed"] = _RNG.random()

    s = _state("lightning", n, init)
    s["next"] -= 1.0 / 30.0
    if s["next"] <= 0.0:
        s["flash"] = 1.0
        s["next"] = 0.8 + _RNG.random() * 2.6
        s["seed"] = _RNG.random()
    s["flash"] *= 0.78
    f = s["flash"]
    c1, c2 = p["c1"], p["c2"]
    for i in range(n):
        pos = i / n
        wobble = 0.5 + 0.5 * math.sin(pos * 9.0 + s["seed"] * 30.0)
        k = f * (0.35 + 0.65 * wobble)
        out[i * 3] = int(c2[0] + (c1[0] - c2[0]) * k)
        out[i * 3 + 1] = int(c2[1] + (c1[1] - c2[1]) * k)
        out[i * 3 + 2] = int(c2[2] + (c1[2] - c2[2]) * k)


def _fx_load(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    """按 CPU/GPU 负载填充，颜色由低到高从青绿过渡到洋红。"""
    load = max(0.0, min(1.0, p.get("load", 0.0)))
    fill = load
    lut = pal_lut(p["pal"])
    for i in range(n):
        pos = i / n
        if pos < fill:
            k = 0.35 + 0.65 * pos
            r, g, b = lut[int(pos * 512.0) & 511]
            out[i * 3] = int(r * k)
            out[i * 3 + 1] = int(g * k)
            out[i * 3 + 2] = int(b * k)
        else:
            out[i * 3] = 6
            out[i * 3 + 1] = 6
            out[i * 3 + 2] = 12


def _fx_heartbeat(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    x = (st * 0.55) % 1.0
    # 双峰心跳
    k = math.exp(-((x - 0.10) ** 2) / 0.0022) + 0.62 * math.exp(-((x - 0.30) ** 2) / 0.0030)
    k = min(1.0, 0.04 + k)
    c = p["c1"]
    for i in range(n):
        out[i * 3] = int(c[0] * k)
        out[i * 3 + 1] = int(c[1] * k)
        out[i * 3 + 2] = int(c[2] * k)


def _fx_wave(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    c1, c2 = p["c1"], p["c2"]
    freq = 1.0 + p["size"] * 3.0
    for i in range(n):
        pos = i / n
        k = 0.5 + 0.5 * math.sin((pos * freq - st * 0.35) * math.tau)
        out[i * 3] = int(c1[0] + (c2[0] - c1[0]) * k)
        out[i * 3 + 1] = int(c1[1] + (c2[1] - c1[1]) * k)
        out[i * 3 + 2] = int(c1[2] + (c2[2] - c1[2]) * k)


def _fx_bounce(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    size = max(0.03, p["size"] * 0.35)
    # 三角波做弹跳
    x = (st * 0.42) % 2.0
    if x > 1.0:
        x = 2.0 - x
    c = p["c1"]
    bg = p["c2"]
    for i in range(n):
        pos = i / n
        d = pos - x
        k = math.exp(-(d * d) / (2.0 * size * size))
        out[i * 3] = int(bg[0] + (c[0] - bg[0]) * k)
        out[i * 3 + 1] = int(bg[1] + (c[1] - bg[1]) * k)
        out[i * 3 + 2] = int(bg[2] + (c[2] - bg[2]) * k)


def _fx_aurora(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    """多层正弦叠加出来的流动极光，颜色走调色板。"""
    lut = pal_lut(p["pal"])
    s1 = math.sin(st * 0.35)
    s2 = math.sin(st * 0.21 + 1.7)
    s3 = math.sin(st * 0.57 + 3.1)
    for i in range(n):
        pos = i / n
        v = (
            math.sin(pos * math.tau * 1.0 + s1 * 2.2)
            + 0.65 * math.sin(pos * math.tau * 2.0 - s2 * 1.6)
            + 0.35 * math.sin(pos * math.tau * 3.0 + s3)
        )
        v = 0.5 + 0.5 * (v / 2.0)
        r, g, b = lut[int((v * 0.85 + st * 0.05) % 1.0 * 512.0) & 511]
        k = 0.28 + 0.72 * v
        out[i * 3] = int(r * k)
        out[i * 3 + 1] = int(g * k)
        out[i * 3 + 2] = int(b * k)


def _fx_meteor(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    count = 3
    size = max(0.03, p["size"] * 0.3)
    lut = pal_lut(p["pal"])
    for i in range(n):
        out[i * 3] = 0
        out[i * 3 + 1] = 0
        out[i * 3 + 2] = 0
    for m in range(count):
        head = ((st * (0.25 + m * 0.07) + m * 0.37) % 1.0)
        col = lut[int((m / count) * 512.0) & 511]
        for i in range(n):
            pos = i / n
            d = (head - pos) % 1.0
            k = math.exp(-(d * d) / (2.0 * size * size * 0.08))
            if d > 0.3:
                continue
            j = i * 3
            out[j] = min(255, out[j] + int(col[0] * k))
            out[j + 1] = min(255, out[j + 1] + int(col[1] * k))
            out[j + 2] = min(255, out[j + 2] + int(col[2] * k))


def _fx_wipe(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    lut = pal_lut(p["pal"])
    seg = 1.0
    total = (st * 0.28) % (seg * 2.0)
    if total < seg:
        prog = total / seg
        col = lut[int(st * 0.28 / (seg * 2.0) * 512.0) & 511]
    else:
        prog = 1.0 - (total - seg) / seg
        col = lut[int(st * 0.28 / (seg * 2.0) * 512.0) & 511]
    cut = int(prog * n)
    for i in range(n):
        j = i * 3
        if i < cut:
            out[j] = col[0]
            out[j + 1] = col[1]
            out[j + 2] = col[2]
        else:
            out[j] = 8
            out[j + 1] = 8
            out[j + 2] = 10


def _fx_police(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    x = (st * 1.6) % 1.0
    left = x < 0.5
    k = math.sin((x % 0.5) * math.tau * 2.0) ** 2
    k = 0.15 + 0.85 * k
    cA = (255, 0, 40) if left else (20, 60, 255)
    cB = (0, 0, 0)
    for i in range(n):
        pos = i / n
        if left and pos < 0.5:
            c = cA
        elif (not left) and pos >= 0.5:
            c = cA
        else:
            c = cB
        out[i * 3] = int(c[0] * k)
        out[i * 3 + 1] = int(c[1] * k)
        out[i * 3 + 2] = int(c[2] * k)


def _fx_stacks(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    """模拟频谱柱：每颗灯独立起伏。"""
    lut = pal_lut(p["pal"])
    for i in range(n):
        h = (i * 2246822519) & 0xFFFFFFFF
        phase = (h % 628) / 100.0
        spd = 1.0 + ((h >> 9) % 100) / 55.0
        v = 0.5 + 0.5 * math.sin(st * spd * 0.9 + phase)
        v = v ** 1.6
        r, g, b = lut[int((i / n * 0.6 + st * 0.06) % 1.0 * 512.0) & 511]
        k = 0.12 + 0.88 * v
        out[i * 3] = int(r * k)
        out[i * 3 + 1] = int(g * k)
        out[i * 3 + 2] = int(b * k)


def _fx_plasma(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    lut = pal_lut(p["pal"])
    a = math.sin(st * 0.4)
    for i in range(n):
        pos = i / n
        v = (
            math.sin(pos * 12.0 + a * 3.0)
            + math.sin(pos * 7.0 - st * 0.9)
            + math.sin((pos + st * 0.15) * 18.0)
        ) / 3.0
        t2 = 0.5 + 0.5 * v
        r, g, b = lut[int(t2 * 512.0) & 511]
        out[i * 3] = r
        out[i * 3 + 1] = g
        out[i * 3 + 2] = b


def _fx_fade_trail(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    """每颗灯独立地随机点亮再缓慢熄灭。"""
    def init(s):
        s["v"] = [0.0] * max(1, n)
        s["hue"] = [0.0] * max(1, n)

    s = _state("fade", n, init)
    v = s["v"]
    hu = s["hue"]
    for i in range(n):
        if v[i] <= 0.01 and _RNG.random() < 0.03:
            v[i] = 1.0
            hu[i] = _RNG.random()
        else:
            v[i] *= 0.985
        r, g, b = _HUE_LUT[int(hu[i] * 512.0) & 511]
        k = v[i]
        out[i * 3] = int(r * k)
        out[i * 3 + 1] = int(g * k)
        out[i * 3 + 2] = int(b * k)


def _fx_temp(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    """温度律动：灯色跟随 CPU 温度，22°C 冷蓝 → 92°C 橙红。

    温度来自风扇模块（同一套传感器），没有数据时退化为静态青色。
    超过 90°C 会加一层快速脉冲，肉眼一眼能看出"烫了"。
    """
    temp = p.get("temp")
    if temp is None:
        temp = 45.0
    k = max(0.0, min(1.0, (float(temp) - 22.0) / 70.0))
    base = hue(0.58 * (1.0 - k))
    gain = 0.55 + 0.45 * k
    if k > 0.9:
        gain *= 0.82 + 0.18 * math.sin(st * 7.0)
    flow = st * 0.22
    for i in range(n):
        pos = i / n
        w = 0.5 + 0.5 * math.sin((pos - flow) * math.tau)
        kk = gain * (0.70 + 0.30 * w)
        out[i * 3] = int(base[0] * kk)
        out[i * 3 + 1] = int(base[1] * kk)
        out[i * 3 + 2] = int(base[2] * kk)


def _fx_sunset(t: float, st: float, n: int, p: dict, out: bytearray) -> None:
    """暖色渐变缓慢游走，适合当桌面氛围灯。"""
    lut = pal_lut("日落")
    for i in range(n):
        pos = (i / n * 0.55 + st * 0.06) % 1.0
        r, g, b = lut[int(pos * 512.0) & 511]
        k = 0.55 + 0.45 * math.sin(pos * math.tau)
        out[i * 3] = int(r * k)
        out[i * 3 + 1] = int(g * k)
        out[i * 3 + 2] = int(b * k)


# ---------------------------------------------------------------- 效果注册表

@dataclass
class EffectSpec:
    id: str
    name: str
    hint: str
    fn: Callable
    color_mode: str = "dual"   # single / dual / palette
    speed: float = 1.0
    size: float = 0.35
    section: str = "常用"


EFFECTS: List[EffectSpec] = [
    EffectSpec("static", "静态常亮", "单色恒亮，最省电", _fx_static, "single", 1.0, 0.35, "常用"),
    EffectSpec("breathing", "呼吸灯", "柔和明暗起伏", _fx_breathing, "single", 1.0, 0.35, "常用"),
    EffectSpec("rainbow", "彩虹流光", "整条灯带流动的七彩", _fx_rainbow_multi, "palette", 1.0, 0.35, "常用"),
    EffectSpec("rainbow_breath", "彩虹呼吸", "七彩随时间明暗", _fx_rainbow_breath, "palette", 1.0, 0.35, "常用"),
    EffectSpec("chase", "跑马灯", "亮点带尾巴循环奔跑", _fx_chase, "palette", 1.0, 0.30, "常用"),
    EffectSpec("comet", "彗星", "单颗光点带长尾扫过", _fx_comet, "dual", 1.0, 0.35, "常用"),
    EffectSpec("gradient", "渐变流动", "双色渐变缓缓流转", _fx_gradient, "dual", 1.0, 0.35, "常用"),
    EffectSpec("color_cycle", "色相循环", "整体颜色平滑转圈", _fx_color_cycle, "palette", 1.0, 0.35, "常用"),

    EffectSpec("aurora", "极光", "多层波叠加的流动光带", _fx_aurora, "palette", 1.0, 0.40, "氛围"),
    EffectSpec("plasma", "等离子", "经典等离子纹理", _fx_plasma, "palette", 1.0, 0.35, "氛围"),
    EffectSpec("sunset", "日落", "暖色氛围缓慢游走", _fx_sunset, "palette", 1.0, 0.35, "氛围"),
    EffectSpec("wave", "波浪", "正弦明暗波向前推进", _fx_wave, "dual", 1.0, 0.35, "氛围"),
    EffectSpec("scanner", "扫描", "光条来回巡视", _fx_scanner, "dual", 1.0, 0.30, "氛围"),
    EffectSpec("ripple", "涟漪", "从中心一圈圈扩散", _fx_ripple, "dual", 1.0, 0.35, "氛围"),

    EffectSpec("twinkle", "星空闪烁", "散落的星点随机明灭", _fx_twinkle, "palette", 1.0, 0.35, "动感"),
    EffectSpec("fire", "火焰", "从底部窜起的火苗", _fx_fire, "single", 1.0, 0.55, "动感"),
    EffectSpec("meteor", "流星雨", "多颗流星同时划过", _fx_meteor, "palette", 1.0, 0.35, "动感"),
    EffectSpec("bounce", "弹球", "光点在两端来回反弹", _fx_bounce, "dual", 1.0, 0.35, "动感"),
    EffectSpec("stacks", "频谱", "每颗灯独立起伏像均衡器", _fx_stacks, "palette", 1.0, 0.35, "动感"),
    EffectSpec("fade_trail", "随机星火", "灯珠随机点亮再慢慢熄灭", _fx_fade_trail, "palette", 1.0, 0.35, "动感"),
    EffectSpec("wipe", "擦除循环", "颜色逐颗铺满再退去", _fx_wipe, "palette", 1.0, 0.35, "动感"),

    EffectSpec("load", "负载律动", "灯带长度跟随 CPU / GPU 占用", _fx_load, "palette", 1.0, 0.35, "实用"),
    EffectSpec("temp", "温度律动", "灯色随 CPU 温度从冷蓝烧到橙红", _fx_temp, "none", 1.0, 0.35, "实用"),
    EffectSpec("heartbeat", "心跳", "双峰脉冲，安静房间很有感", _fx_heartbeat, "single", 1.0, 0.35, "实用"),
    EffectSpec("lightning", "雷暴", "随机闪电，带一点刺激", _fx_lightning, "dual", 1.0, 0.35, "实用"),
    EffectSpec("police", "警示灯", "左右红蓝交替", _fx_police, "none", 1.0, 0.35, "实用"),
]

EFFECT_MAP: Dict[str, EffectSpec] = {e.id: e for e in EFFECTS}
SECTIONS = ["常用", "氛围", "动感", "实用"]


def default_params() -> dict:
    return {
        "c1": (0, 190, 255),
        "c2": (20, 0, 40),
        "pal": "彩虹",
        "speed": 1.0,
        "dir": 1,
        "size": 0.35,
        "load": 0.0,
    }
