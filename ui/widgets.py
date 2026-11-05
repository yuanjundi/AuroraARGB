"""自绘控件：灯带预览、色环、开关、设备卡片等。"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize,
    Qt, Signal, Property,
)
from PySide6.QtGui import (
    QBrush, QColor, QConicalGradient, QFont, QFontMetrics, QImage, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
    QWidget,
)

from . import theme as T


# ---------------------------------------------------------------- 灯带预览

def _soften(cols: List[Tuple[int, int, int]], passes: int = 2) -> List[Tuple[int, int, int]]:
    """对采样色做轻度邻域平滑。

    灯珠很密时相邻两颗的颜色差可能很大（例如火焰），直接放大成光带会出现
    一条条竖向"栅栏"。这里做两次 3 抽头平滑，视觉上更接近真实灯带的光扩散。
    """
    n = len(cols)
    if n < 3:
        return cols
    r = [[c[0], c[1], c[2]] for c in cols]
    for _ in range(passes):
        prev = r[0]
        for i in range(1, n - 1):
            cur = r[i]
            nxt = r[i + 1]
            r[i] = ((cur[0] * 2 + prev[0] + nxt[0]) >> 2,
                    (cur[1] * 2 + prev[1] + nxt[1]) >> 2,
                    (cur[2] * 2 + prev[2] + nxt[2]) >> 2)
            prev = cur
    return [(c[0], c[1], c[2]) for c in r]


class GlowStrip(QWidget):
    """把一条灯带渲染成发光效果，视觉上是界面的主角。"""

    DISPLAY_POINTS = 96

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._colors: List[Tuple[int, int, int]] = [(0, 0, 0)] * self.DISPLAY_POINTS
        self._sig: bytes = b""
        self._label = ""
        self._sub = ""
        self._offline = False

    def set_frame(self, buf: bytes, led_count: int) -> None:
        if not buf:
            return
        src_n = len(buf) // 3
        if src_n <= 0:
            return
        # 灯珠不多时直接用全部灯珠，保证色阶足够细，避免出现竖条纹
        pts = max(2, min(src_n, 256))
        cols: List[Tuple[int, int, int]] = []
        for i in range(pts):
            s = int(i / (pts - 1) * (src_n - 1)) if src_n > 1 else 0
            j = s * 3
            cols.append((buf[j], buf[j + 1], buf[j + 2]))
        sig = bytes([c for col in cols for c in col])
        if sig == self._sig:
            return
        self._sig = sig
        if len(cols) > 24:
            # 灯珠越多，相邻色差堆得越密，平滑次数要跟着加
            passes = max(2, min(8, len(cols) // 30))
            cols = _soften(cols, passes)
        self._colors = cols
        self.update()

    def set_label(self, label: str, sub: str = "") -> None:
        if label != self._label or sub != self._sub:
            self._label = label
            self._sub = sub
            self.update()

    def set_offline(self, offline: bool) -> None:
        if offline != self._offline:
            self._offline = offline
            self.update()

    def _build_glow(self, w: int, h: int) -> QPixmap:
        """按半分辨率离屏渲染光带，再放大贴到卡片上。

        大窗口 + 高 DPI 下如果按物理像素逐帧生成渐变会明显掉帧，
        半分辨率能把绘制开销降到四分之一，肉眼几乎看不出差别。
        """
        W = max(48, int(w * 0.5))
        H = max(24, int(h * 0.5))
        n = len(self._colors)
        band_h = max(12, int(H * 0.34))

        img = QImage(n, 1, QImage.Format.Format_ARGB32)
        for i, c in enumerate(self._colors):
            img.setPixelColor(i, 0, QColor(c[0], c[1], c[2], 255))
        band = QPixmap.fromImage(
            img.scaled(W, band_h,
                       Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation))
        p2 = QPainter(band)
        p2.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        g = QLinearGradient(0, 0, 0, band_h)
        g.setColorAt(0.00, QColor(0, 0, 0, 0))
        g.setColorAt(0.34, QColor(0, 0, 0, 110))
        g.setColorAt(0.50, QColor(0, 0, 0, 208))
        g.setColorAt(0.66, QColor(0, 0, 0, 110))
        g.setColorAt(1.00, QColor(0, 0, 0, 0))
        p2.fillRect(0, 0, W, band_h, QBrush(g))
        p2.end()

        pm = QPixmap(W, H)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        y = H * 0.52

        halo = band.scaled(int(W * 1.06), int(band_h * 1.55),
                           Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        p.setOpacity(0.30)
        p.drawPixmap(int(-W * 0.03), int(y - halo.height() / 2.0), halo)
        p.setOpacity(1.0)
        p.drawPixmap(0, int(y - band_h / 2.0), band)

        p.save()
        p.translate(0, y * 2 + 4)
        p.scale(1.0, -0.5)
        p.setOpacity(0.38)
        p.drawPixmap(0, int(y - band_h / 2.0), band)
        p.restore()
        p.end()
        return pm

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()
        rect = QRectF(0.5, 0.5, w - 1, h - 1)

        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        p.fillPath(path, QColor("#0B0F16"))
        p.setPen(QPen(QColor(T.BORDER), 1))
        p.drawPath(path)

        top = QLinearGradient(0, 0, 0, h * 0.7)
        top.setColorAt(0.0, QColor(60, 90, 140, 26))
        top.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.save()
        p.setClipPath(path)
        p.fillPath(path, QBrush(top))
        p.restore()

        if self._colors and any((c[0] + c[1] + c[2]) > 6 for c in self._colors):
            glow = self._build_glow(w, h)
            p.save()
            p.setClipPath(path)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawPixmap(QRectF(0, 0, w, h), glow, QRectF(glow.rect()))
            p.restore()

        # 文字
        p.setPen(QColor(T.TEXT))
        f = QFont(T.FONT, 12)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.drawText(QRectF(22, 16, w - 44, 24), Qt.AlignmentFlag.AlignLeft, self._label)
        if self._sub:
            f2 = QFont(T.FONT, 9)
            p.setFont(f2)
            p.setPen(QColor(T.SUB))
            p.drawText(QRectF(22, 36, w - 44, 20), Qt.AlignmentFlag.AlignLeft, self._sub)

        if self._offline:
            p.setPen(QColor(255, 92, 114, 200))
            f3 = QFont(T.FONT, 9)
            p.setFont(f3)
            p.drawText(QRectF(0, h - 26, w - 22, 20),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       "设备未连接 · 当前为预览")


# ---------------------------------------------------------------- 色环

class ColorWheel(QWidget):
    """色环 + SV 方块，紧凑且直观的取色器。"""

    color_changed = Signal(tuple)

    def __init__(self, color: Tuple[int, int, int] = (0, 190, 255),
                 size: int = 140, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._h = 0.5
        self._s = 1.0
        self._v = 1.0
        self._drag = ""    # "ring" / "sv"
        self.set_color(color, emit=False)
        self._img: Optional[QPixmap] = None
        self._img_key = None

    def _geometry(self):
        R = min(self.width(), self.height()) / 2.0 - 2
        outer = R
        inner = R - 13.0
        side = inner * 1.22
        sq = QRectF(self.width() / 2 - side / 2, self.height() / 2 - side / 2, side, side)
        return outer, inner, sq

    def color(self) -> Tuple[int, int, int]:
        from core import colors as C
        return C.hsv_to_rgb(self._h, self._s, self._v)

    def set_color(self, rgb: Tuple[int, int, int], emit: bool = False) -> None:
        from core import colors as C
        h, s, v = C.rgb_to_hsv(rgb)
        if s <= 0.001:
            h = self._h
        self._h, self._s, self._v = h, max(s, 0.0), max(v, 0.05)
        self.update()
        if emit:
            self.color_changed.emit(self.color())

    def _rebuild_hue_ring(self) -> None:
        outer, inner, _ = self._geometry()
        d = int(outer * 2) + 4
        pm = QPixmap(d, d)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        grad = QConicalGradient(d / 2.0, d / 2.0, 0)
        for i in range(0, 361, 6):
            grad.setColorAt(i / 360.0, QColor.fromHsvF(((i % 360) / 360.0), 1.0, 1.0))
        path = QPainterPath()
        path.addEllipse(QPointF(d / 2.0, d / 2.0), outer, outer)
        path.addEllipse(QPointF(d / 2.0, d / 2.0), inner, inner)
        path.setFillRule(Qt.FillRule.OddEvenFill)
        p.fillPath(path, QBrush(grad))
        p.end()
        self._img = pm
        self._img_key = (d, outer, inner)

    def resizeEvent(self, e) -> None:
        self._rebuild_hue_ring()
        super().resizeEvent(e)

    def paintEvent(self, e) -> None:
        outer, inner, sq = self._geometry()
        if self._img is None or self._img_key is None or self._img_key[0] != int(outer * 2) + 4:
            self._rebuild_hue_ring()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        p.drawPixmap(3, 3, self._img)

        # SV 方块
        hue_color = QColor.fromHsvF(self._h, 1.0, 1.0)
        g1 = QLinearGradient(sq.topLeft(), sq.topRight())
        g1.setColorAt(0.0, QColor(255, 255, 255))
        g1.setColorAt(1.0, hue_color)
        p.fillRect(sq, QBrush(g1))
        g2 = QLinearGradient(sq.topLeft(), sq.bottomLeft())
        g2.setColorAt(0.0, QColor(0, 0, 0, 0))
        g2.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(sq, QBrush(g2))
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(sq)

        # 环上的指示点
        cx, cy = self.width() / 2.0, self.height() / 2.0
        ang = self._h * math.tau
        rr = (outer + inner) / 2.0
        hx = cx + math.cos(ang) * rr
        hy = cy + math.sin(ang) * rr
        p.setPen(QPen(QColor(255, 255, 255, 235), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(hx, hy), 5.5, 5.5)

        # SV 上的指示点
        sx = sq.left() + self._s * sq.width()
        sy = sq.top() + (1.0 - self._v) * sq.height()
        p.setPen(QPen(QColor(0, 0, 0, 120), 3))
        p.drawEllipse(QPointF(sx, sy), 5.5, 5.5)
        p.setPen(QPen(QColor(255, 255, 255, 240), 1.6))
        p.drawEllipse(QPointF(sx, sy), 5.5, 5.5)

    def _apply_pos(self, pos: QPointF) -> None:
        outer, inner, sq = self._geometry()
        cx, cy = self.width() / 2.0, self.height() / 2.0
        if self._drag == "ring":
            ang = math.atan2(pos.y() - cy, pos.x() - cx)
            self._h = (ang / math.tau) % 1.0
        elif self._drag == "sv":
            self._s = max(0.0, min(1.0, (pos.x() - sq.left()) / max(1.0, sq.width())))
            self._v = max(0.04, min(1.0, 1.0 - (pos.y() - sq.top()) / max(1.0, sq.height())))
        self.update()
        self.color_changed.emit(self.color())

    def mousePressEvent(self, e) -> None:
        outer, inner, sq = self._geometry()
        pos = QPointF(e.position())
        cx, cy = self.width() / 2.0, self.height() / 2.0
        dist = math.hypot(pos.x() - cx, pos.y() - cy)
        if sq.contains(pos):
            self._drag = "sv"
        elif dist >= inner - 4:
            self._drag = "ring"
        else:
            self._drag = "sv"
        self._apply_pos(pos)

    def mouseMoveEvent(self, e) -> None:
        if self._drag:
            self._apply_pos(QPointF(e.position()))

    def mouseReleaseEvent(self, e) -> None:
        self._drag = ""


# ---------------------------------------------------------------- 开关

class ToggleSwitch(QAbstractButton):
    def __init__(self, checked: bool = True, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(42, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._on_toggle)

    def _on_toggle(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def get_knob(self) -> float:
        return self._pos

    def set_knob(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, get_knob, set_knob)

    def sync(self, on: bool) -> None:
        """外部改变状态时同步外观，同时保留动画。"""
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._on_toggle(on)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect().adjusted(1, 1, -1, -1)
        on = self._pos
        if on > 0.01:
            grad = QLinearGradient(r.left(), 0, r.right(), 0)
            c1 = QColor(T.ACCENT)
            c2 = QColor(T.ACCENT2)
            c1.setAlpha(int(60 + 195 * on))
            c2.setAlpha(int(60 + 195 * on))
            grad.setColorAt(0, c1)
            grad.setColorAt(1, c2)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setBrush(QColor(T.PANEL3))
            p.setPen(QPen(QColor(T.BORDER_L), 1))
        p.drawRoundedRect(r, r.height() / 2.0, r.height() / 2.0)
        kx = r.left() + r.height() / 2.0 + on * (r.width() - r.height())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255) if on > 0.5 else QColor(150, 160, 180))
        p.drawEllipse(QPointF(kx, r.center().y()), r.height() / 2.0 - 3, r.height() / 2.0 - 3)


# ---------------------------------------------------------------- 灯效按钮

class EffectButton(QAbstractButton):
    def __init__(self, text: str, accent: Tuple[int, int, int] = (61, 220, 255),
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self._accent = QColor(*accent)
        self._hover = False

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        checked = self.isChecked()
        if checked:
            grad = QLinearGradient(r.left(), 0, r.right(), 0)
            grad.setColorAt(0.0, QColor(61, 220, 255, 34))
            grad.setColorAt(1.0, QColor(139, 92, 246, 26))
            p.setBrush(QBrush(grad))
            p.setPen(QPen(QColor(61, 220, 255, 120), 1))
        elif self._hover:
            p.setBrush(QColor(T.PANEL3))
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 9, 9)

        # 左侧小光点
        dot_c = self._accent if checked else QColor(T.DIM)
        if checked:
            glow = QRadialGradient(20, r.center().y(), 9)
            glow.setColorAt(0, QColor(dot_c.red(), dot_c.green(), dot_c.blue(), 150))
            glow.setColorAt(1, QColor(dot_c.red(), dot_c.green(), dot_c.blue(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(20, r.center().y()), 9, 9)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(dot_c)
        p.drawEllipse(QPointF(20, r.center().y()), 3.0, 3.0)

        f = QFont(T.FONT, 10)
        if checked:
            f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(T.TEXT) if checked else QColor(T.SUB))
        p.drawText(QRectF(32, 0, r.width() - 36, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())


# ---------------------------------------------------------------- 设备卡片

class DeviceCard(QFrame):
    toggled = Signal(bool)

    def __init__(self, name: str, sub: str, kind: str = "mb",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("CardFlat")
        self.setFixedHeight(66)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 12, 10)
        lay.setSpacing(10)

        self._dot = _StatusDot()
        lay.addWidget(self._dot)

        col = QVBoxLayout()
        col.setSpacing(1)
        self._name = QLabel(name)
        self._name.setStyleSheet("font-size:13px;font-weight:600;color:%s;" % T.TEXT)
        self._sub = QLabel(sub)
        self._sub.setStyleSheet("font-size:11px;color:%s;" % T.SUB)
        col.addWidget(self._name)
        col.addWidget(self._sub)
        lay.addLayout(col, 1)

        self.switch = ToggleSwitch(True)
        self.switch.toggled.connect(self.toggled.emit)
        lay.addWidget(self.switch)
        self._kind = kind

    def set_online(self, online: bool) -> None:
        self._dot.set_state(online)
        self._sub.setStyleSheet("font-size:11px;color:%s;" % (T.SUB if online else T.ERR))

    def set_sub(self, text: str) -> None:
        self._sub.setText(text)


class _StatusDot(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self._on = False

    def set_state(self, on: bool) -> None:
        self._on = on
        self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = QColor(T.OK) if self._on else QColor(T.ERR)
        glow = QRadialGradient(10, 10, 9)
        glow.setColorAt(0, QColor(c.red(), c.green(), c.blue(), 130))
        glow.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(10, 10), 9, 9)
        p.setBrush(c)
        p.drawEllipse(QPointF(10, 10), 3.4, 3.4)


# ---------------------------------------------------------------- 分段选择

class Segmented(QWidget):
    changed = Signal(int)

    def __init__(self, items: Sequence[str], index: int = 0,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._items = list(items)
        self._index = index
        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = -1

    def set_index(self, i: int) -> None:
        if 0 <= i < len(self._items) and i != self._index:
            self._index = i
            self.update()
            self.changed.emit(i)

    def index(self) -> int:
        return self._index

    def _seg_rects(self):
        w = self.width() / max(1, len(self._items))
        return [QRectF(i * w + 2, 2, w - 4, self.height() - 4) for i in range(len(self._items))]

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.PANEL3))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 8, 8)
        for i, r in enumerate(self._seg_rects()):
            if i == self._index:
                grad = QLinearGradient(r.left(), 0, r.right(), 0)
                grad.setColorAt(0, QColor(61, 220, 255, 46))
                grad.setColorAt(1, QColor(139, 92, 246, 34))
                p.setBrush(QBrush(grad))
                p.setPen(QPen(QColor(61, 220, 255, 90), 1))
                p.drawRoundedRect(r, 6, 6)
            f = QFont(T.FONT, 9)
            p.setFont(f)
            p.setPen(QColor(T.TEXT) if i == self._index else QColor(T.SUB))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._items[i])

    def mousePressEvent(self, e) -> None:
        for i, r in enumerate(self._seg_rects()):
            if r.contains(QPointF(e.position())):
                self.set_index(i)
                break


# ---------------------------------------------------------------- 参数行

class SliderRow(QWidget):
    value_changed = Signal(float)

    def __init__(self, title: str, value: float = 0.5, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(50)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(2)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self._t = QLabel(title)
        self._t.setStyleSheet("font-size:12px;color:%s;" % T.SUB)
        self._v = QLabel("")
        self._v.setStyleSheet("font-size:12px;color:%s;font-weight:600;" % T.TEXT)
        self._v.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(self._t, 1)
        row.addWidget(self._v)
        lay.addLayout(row)

        from PySide6.QtWidgets import QSlider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(int(value * 1000))
        self.slider.valueChanged.connect(self._on_change)
        lay.addWidget(self.slider)
        self._fmt = lambda v: "%d%%" % int(v * 100)
        self._on_change(self.slider.value())

    def set_formatter(self, fn) -> None:
        self._fmt = fn
        self._on_change(self.slider.value())

    def set_value(self, v: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(max(0.0, min(1.0, v)) * 1000))
        self.slider.blockSignals(False)
        self._on_change(self.slider.value())

    def value(self) -> float:
        return self.slider.value() / 1000.0

    def _on_change(self, iv: int) -> None:
        v = iv / 1000.0
        self._v.setText(self._fmt(v))
        self.value_changed.emit(v)


class SectionTitle(QLabel):
    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text.upper(), parent)
        self.setProperty("role", "sec")
        self.setStyleSheet("font-size:10px;font-weight:700;color:%s;letter-spacing:1.4px;"
                           "padding-top:6px;" % T.DIM)


# ---------------------------------------------------------------- 场景预设

class PresetCard(QFrame):
    """一键套用「效果 + 配色 + 亮度」的场景卡片。"""

    clicked = Signal()

    def __init__(self, name: str, desc: str, colors: Sequence,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(84)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._name = name
        self._desc = desc
        self._colors = [QColor(*c) for c in colors]
        self._hover = False

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(T.BORDER_L if self._hover else T.BORDER), 1))
        p.setBrush(QColor(T.PANEL2 if not self._hover else "#1B2130"))
        p.drawRoundedRect(r, 12, 12)

        # 顶部配色条
        bar = QRectF(14, 14, self.width() - 28, 7)
        grad = QLinearGradient(bar.left(), 0, bar.right(), 0)
        n = max(1, len(self._colors) - 1)
        for i, c in enumerate(self._colors):
            grad.setColorAt(i / n, c)
        clip = QPainterPath()
        clip.addRoundedRect(bar, 3.5, 3.5)
        p.setClipPath(clip)
        p.fillRect(bar, QBrush(grad))
        p.setClipping(False)

        f = QFont(T.FONT, 10)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(T.TEXT))
        p.drawText(QRectF(14, 28, self.width() - 28, 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._name)

        f2 = QFont(T.FONT, 8)
        p.setFont(f2)
        p.setPen(QColor(T.SUB))
        p.drawText(QRectF(14, 48, self.width() - 28, 24),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self._desc)
