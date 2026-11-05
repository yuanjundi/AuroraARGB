"""颜色工具：HSV 转换、调色板、平滑插值。

所有颜色均为 0-255 的 (r, g, b) 三元组。
"""
from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

RGB = Tuple[int, int, int]


def clamp8(v: float) -> int:
    if v <= 0:
        return 0
    if v >= 255:
        return 255
    return int(v)


def clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def hsv_to_rgb(h: float, s: float, v: float) -> RGB:
    """h/s/v 均为 0..1，h 自动取模。"""
    h = h % 1.0
    s = clamp01(s)
    v = clamp01(v)
    if s <= 0.0:
        c = clamp8(v * 255.0)
        return (c, c, c)
    h6 = h * 6.0
    i = int(h6)
    f = h6 - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return (clamp8(r * 255.0), clamp8(g * 255.0), clamp8(b * 255.0))


def rgb_to_hsv(c: RGB) -> Tuple[float, float, float]:
    r, g, b = c[0] / 255.0, c[1] / 255.0, c[2] / 255.0
    mx = max(r, g, b)
    mn = min(r, g, b)
    d = mx - mn
    if d <= 1e-9:
        return (0.0, 0.0, mx)
    if mx == r:
        h = ((g - b) / d) % 6.0
    elif mx == g:
        h = (b - r) / d + 2.0
    else:
        h = (r - g) / d + 4.0
    return (h / 6.0, d / mx, mx)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_rgb(c1: RGB, c2: RGB, t: float) -> RGB:
    t = clamp01(t)
    return (
        clamp8(c1[0] + (c2[0] - c1[0]) * t),
        clamp8(c1[1] + (c2[1] - c1[1]) * t),
        clamp8(c1[2] + (c2[2] - c1[2]) * t),
    )


def scale_rgb(c: RGB, k: float) -> RGB:
    if k <= 0.0:
        return (0, 0, 0)
    if k >= 1.0:
        return c
    return (clamp8(c[0] * k), clamp8(c[1] * k), clamp8(c[2] * k))


def add_rgb(a: RGB, b: RGB) -> RGB:
    return (clamp8(a[0] + b[0]), clamp8(a[1] + b[1]), clamp8(a[2] + b[2]))


def to_hex(c: RGB) -> str:
    return "#%02x%02x%02x" % (c[0], c[1], c[2])


def from_hex(s: str) -> RGB:
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return (255, 255, 255)


# ---------------------------------------------------------------- 调色板

PALETTES = {
    "彩虹": [
        (255, 0, 0), (255, 96, 0), (255, 200, 0), (120, 255, 0),
        (0, 255, 90), (0, 220, 255), (0, 110, 255), (110, 0, 255), (255, 0, 160),
    ],
    "日落": [(255, 60, 0), (255, 120, 30), (255, 180, 60), (255, 90, 110), (180, 40, 120)],
    "海洋": [(0, 40, 120), (0, 100, 200), (0, 180, 220), (60, 230, 220), (10, 140, 180)],
    "赛博": [(255, 0, 128), (128, 0, 255), (0, 200, 255), (0, 255, 180)],
    "森林": [(0, 80, 40), (20, 160, 60), (120, 220, 80), (0, 200, 160), (60, 120, 40)],
    "火焰": [(120, 0, 0), (200, 40, 0), (255, 110, 0), (255, 200, 40), (255, 255, 200)],
    "糖果": [(255, 120, 180), (255, 200, 220), (180, 160, 255), (120, 220, 255), (255, 240, 160)],
    "冰霜": [(20, 60, 160), (60, 140, 230), (140, 210, 255), (230, 250, 255), (90, 170, 220)],
    "极光": [(0, 255, 170), (0, 190, 255), (120, 0, 255), (0, 255, 120), (0, 120, 255)],
}

PALETTE_NAMES = list(PALETTES.keys())


def palette_color(name: str, pos: float) -> RGB:
    """在调色板上按 0..1 取色，闭环插值。"""
    cols: Sequence[RGB] = PALETTES.get(name) or PALETTES["彩虹"]
    n = len(cols)
    if n == 0:
        return (255, 255, 255)
    pos = pos % 1.0
    x = pos * n
    i = int(x)
    f = x - i
    return lerp_rgb(cols[i % n], cols[(i + 1) % n], f)


def gradient(stops: Iterable[RGB], n: int) -> List[RGB]:
    """把任意多色标均匀铺满 n 个灯珠。"""
    stops = list(stops)
    if n <= 0:
        return []
    if not stops:
        stops = [(255, 255, 255)]
    if len(stops) == 1:
        return [stops[0]] * n
    out: List[RGB] = []
    seg = (len(stops) - 1) / max(1, n - 1)
    for i in range(n):
        x = i * seg
        j = int(x)
        if j >= len(stops) - 1:
            out.append(stops[-1])
        else:
            out.append(lerp_rgb(stops[j], stops[j + 1], x - j))
    return out


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 - edge0 < 1e-9:
        return 0.0 if x < edge0 else 1.0
    t = clamp01((x - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def wrap_dist(a: float, b: float, period: float = 1.0) -> float:
    """环上最短距离。"""
    d = abs(a - b) % period
    return min(d, period - d)


def ease_pulse(x: float) -> float:
    """0..1 的平滑脉冲（用于呼吸）。"""
    return 0.5 - 0.5 * math.cos(x * math.tau)
