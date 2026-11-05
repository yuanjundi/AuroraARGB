"""主窗口。"""
from __future__ import annotations

import ctypes
import math
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSizeGrip, QSlider, QSpinBox, QStackedWidget,
    QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
)

from core import autostart as AS
from core import fans as FAN
from .fan_panel import FanPanel, FanRight, FanSide

from core import colors as COLORS
from core import config as CFG
from core import effects as FX
from core import __version__
from core.backends import Channel
from core.backends.colorful import ColorfulBackend
from core.backends.openrgb import OpenRGBBackend
from core.engine import Engine

from . import theme as T
from .widgets import (
    ColorWheel, DeviceCard, EffectButton, GlowStrip, PresetCard, SectionTitle,
    Segmented, SliderRow, ToggleSwitch,
)

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


# ---------------------------------------------------------------- 小部件

class LogoMark(QWidget):
    def __init__(self, size: int = 26, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect()
        cx, cy = r.width() / 2.0, r.height() / 2.0
        rad = min(cx, cy) - 1
        grad = QRadialGradient(cx, cy, rad)
        grad.setColorAt(0.0, QColor(61, 220, 255, 210))
        grad.setColorAt(0.55, QColor(139, 92, 246, 120))
        grad.setColorAt(1.0, QColor(139, 92, 246, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.setPen(QPen(QColor(255, 255, 255, 225), 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(cx - rad * 0.55, cy - rad * 0.55, rad * 1.1, rad * 1.1),
                  60 * 16, 250 * 16)


class WinButton(QAbstractButton):
    def __init__(self, kind: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(34, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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
        if self._hover:
            bg = QColor(255, 92, 114, 210) if self.kind == "close" else QColor(255, 255, 255, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(1, 2, self.width() - 2, self.height() - 4), 6, 6)
        c = QColor("#FFFFFF") if (self._hover and self.kind == "close") else QColor(T.SUB)
        p.setPen(QPen(c, 1.4))
        cx, cy = self.width() / 2.0, self.height() / 2.0
        if self.kind == "close":
            p.drawLine(QPointF(cx - 4, cy - 4), QPointF(cx + 4, cy + 4))
            p.drawLine(QPointF(cx + 4, cy - 4), QPointF(cx - 4, cy + 4))
        elif self.kind == "min":
            p.drawLine(QPointF(cx - 4.5, cy), QPointF(cx + 4.5, cy))
        else:
            p.drawRect(QRectF(cx - 4, cy - 4, 8, 8))


class TitleBar(QWidget):
    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._win = window
        self._drag: Optional[QPoint] = None
        self.setFixedHeight(56)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 10, 0)
        lay.setSpacing(10)

        lay.addWidget(LogoMark(26))
        name = QLabel("AURORA")
        name.setStyleSheet("font-size:15px;font-weight:800;letter-spacing:3.2px;color:%s;" % T.TEXT)
        lay.addWidget(name)
        sub = QLabel("ARGB STUDIO")
        sub.setStyleSheet("font-size:9px;font-weight:600;letter-spacing:1.6px;color:%s;" % T.DIM)
        lay.addWidget(sub)
        lay.addStretch(1)

        self.status_dot = _MiniDot()
        lay.addWidget(self.status_dot)
        self.status_text = QLabel("正在初始化")
        self.status_text.setStyleSheet("font-size:11px;color:%s;" % T.SUB)
        lay.addWidget(self.status_text)

        lay.addSpacing(8)
        self.power = ToggleSwitch(True)
        lay.addWidget(self.power)
        pw = QLabel("输出")
        pw.setStyleSheet("font-size:11px;color:%s;margin-right:6px;" % T.SUB)
        lay.addWidget(pw)

        for kind in ("min", "max", "close"):
            b = WinButton(kind)
            if kind == "min":
                b.clicked.connect(self._win.showMinimized)
            elif kind == "max":
                b.clicked.connect(self._toggle_max)
            else:
                b.clicked.connect(self._win.close)
            lay.addWidget(b)

    def _toggle_max(self) -> None:
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            if self._win.isMaximized():
                return
            self._win.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e) -> None:
        self._drag = None

    def mouseDoubleClickEvent(self, e) -> None:
        self._toggle_max()


class _MiniDot(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._on = False

    def set_state(self, on: bool) -> None:
        self._on = on
        self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = QColor(T.OK) if self._on else QColor(T.WARN)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 50))
        p.drawEllipse(QPointF(7, 7), 6.5, 6.5)
        p.setBrush(c)
        p.drawEllipse(QPointF(7, 7), 3.0, 3.0)


class Swatch(QAbstractButton):
    def __init__(self, palette_name: str, colors: List[Tuple[int, int, int]],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.palette_name = palette_name
        self._colors = colors
        self.setCheckable(True)
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        grad = QLinearGradient(r.left(), 0, r.right(), 0)
        n = max(1, len(self._colors) - 1)
        for i, c in enumerate(self._colors):
            grad.setColorAt(i / n, QColor(*c))
        clip = QPainterPath()
        clip.addRoundedRect(r, 8, 8)
        p.setClipPath(clip)
        p.fillRect(r, QBrush(grad))
        if self.isChecked():
            p.setPen(QPen(QColor(255, 255, 255, 230), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 7, 7)
        else:
            p.setPen(QPen(QColor(0, 0, 0, 40), 1))
            p.drawRoundedRect(r, 8, 8)


# ---------------------------------------------------------------- 主窗口

class MainWindow(QWidget):
    def __init__(self, start_tab: int = 0) -> None:
        super().__init__()
        self._start_tab = start_tab
        self.cfg = CFG.load()
        self.engine = Engine()
        self.backends: Dict[str, object] = {}
        self.channels: List[Channel] = []
        self.cards: Dict[str, DeviceCard] = {}
        self.effect_buttons: Dict[str, EffectButton] = {}
        self._last = time.perf_counter()
        self._stat_acc = 0.0
        self._pv_acc = 0.0
        self._cpu = 0.0
        self._mem = 0.0
        self._proc = None
        self._power_on = True
        self._preview_key: Optional[str] = None
        self._minimized = False
        self._really_quit = False
        self._tray: Optional[QSystemTrayIcon] = None

        self.setWindowTitle("Aurora ARGB Studio")
        self.setMinimumSize(1120, 700)
        w, h = self.cfg.get("window", [1200, 780])
        self.resize(int(w), int(h))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("Root")
        from core.paths import res
        ico = res("app.ico")
        if os.path.isfile(ico):
            self.setWindowIcon(QIcon(ico))
        else:
            self.setWindowIcon(_make_icon())

        self._build()
        self._setup_tray()
        self._apply_config()
        self._scan_devices()
        self._enable_round_corners()

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._last = time.perf_counter()
        self._apply_timer()

        if self._start_tab == 1:
            self.side_tab.set_index(1)
            self._on_side_tab(1)

    # ------------------------------------------------------------ 构建界面

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = TitleBar(self)
        self.titlebar.power.toggled.connect(self._on_power)
        root.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())

        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self._build_center())
        self.fan_panel = FanPanel()
        self.fan_panel.companion = self.fan_side
        self.center_stack.addWidget(self.fan_panel)
        body.addWidget(self.center_stack, 1)

        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._build_right())
        self.fan_right = FanRight(self.fan_panel)
        self.right_stack.addWidget(self.fan_right)
        body.addWidget(self.right_stack)

        root.addLayout(body, 1)
        root.addWidget(self._build_statusbar())

        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        grip.move(self.width() - 16, self.height() - 16)
        grip.raise_()

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("Sidebar")
        panel.setFixedWidth(228)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(14, 16, 10, 10)
        outer.setSpacing(8)

        self.side_tab = Segmented(["灯效", "风扇"])
        self.side_tab.changed.connect(self._on_side_tab)
        outer.addWidget(self.side_tab)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 6, 0)
        il.setSpacing(3)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        current_section = None
        section_colors = {
            "常用": (61, 220, 255),
            "氛围": (139, 92, 246),
            "动感": (255, 120, 180),
            "实用": (56, 224, 160),
        }
        for spec in FX.EFFECTS:
            if spec.section != current_section:
                current_section = spec.section
                il.addSpacing(6)
                t = QLabel(spec.section)
                t.setStyleSheet("font-size:10px;font-weight:700;color:%s;"
                                "letter-spacing:1.2px;padding:4px 6px;" % T.DIM)
                il.addWidget(t)
            b = EffectButton(spec.name, section_colors.get(spec.section, (61, 220, 255)))
            b.setToolTip(spec.hint)
            b.clicked.connect(lambda _=False, eid=spec.id: self._select_effect(eid))
            self._group.addButton(b)
            self.effect_buttons[spec.id] = b
            il.addWidget(b)
        il.addStretch(1)
        scroll.setWidget(inner)
        self.fan_side = FanSide()
        self.side_stack = QStackedWidget()
        self.side_stack.addWidget(scroll)
        self.side_stack.addWidget(self.fan_side)
        outer.addWidget(self.side_stack, 1)

        bottom = QPushButton("刷新设备")
        bottom.setObjectName("Ghost")
        bottom.setCursor(Qt.CursorShape.PointingHandCursor)
        bottom.clicked.connect(self._rescan)
        outer.addWidget(bottom)
        return panel

    def _build_center(self) -> QWidget:
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(22, 16, 22, 14)
        cl.setSpacing(12)

        row = QHBoxLayout()
        row.setSpacing(10)
        title = QLabel("灯效预览")
        title.setStyleSheet("font-size:20px;font-weight:700;color:%s;" % T.TEXT)
        row.addWidget(title)
        self.effect_tag = QLabel("")
        self.effect_tag.setStyleSheet(
            "font-size:11px;color:%s;background:%s;border:1px solid %s;"
            "border-radius:9px;padding:3px 10px;" % (T.ACCENT, T.PANEL2, T.BORDER))
        row.addWidget(self.effect_tag)
        row.addStretch(1)
        self.led_tag = QLabel("")
        self.led_tag.setStyleSheet("font-size:11px;color:%s;" % T.SUB)
        row.addWidget(self.led_tag)
        cl.addLayout(row)

        self.strip = GlowStrip()
        self.strip.setFixedHeight(258)
        cl.addWidget(self.strip)

        dev_head = QHBoxLayout()
        dev_head.addWidget(SectionTitle("设备"))
        dev_head.addStretch(1)
        cl.addLayout(dev_head)

        self.dev_row = QHBoxLayout()
        self.dev_row.setSpacing(10)
        cl.addLayout(self.dev_row)

        cl.addSpacing(2)
        pre_head = QHBoxLayout()
        pre_head.addWidget(SectionTitle("快速场景"))
        pre_head.addStretch(1)
        hint = QLabel("一键套用效果 + 配色 + 亮度")
        hint.setStyleSheet("font-size:11px;color:%s;" % T.DIM)
        pre_head.addWidget(hint)
        cl.addLayout(pre_head)

        self.preset_row = QHBoxLayout()
        self.preset_row.setSpacing(10)
        cl.addLayout(self.preset_row)

        for name, desc, effect, color, bright, pal, speed in PRESETS:
            cols = [color] + list(COLORS.PALETTES.get(pal, [(60, 60, 60)])[:2])
            card = PresetCard(name, desc, cols)
            card.clicked.connect(
                lambda _=None, e=effect, c=color, b=bright, p=pal, s=speed:
                self._apply_preset(e, c, b, p, s))
            self.preset_row.addWidget(card, 1)

        cl.addStretch(1)

        act = QHBoxLayout()
        act.setSpacing(10)
        self.btn_all = QPushButton("全部通道同步")
        self.btn_all.setObjectName("Ghost")
        self.btn_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_all.clicked.connect(self._enable_all)
        act.addWidget(self.btn_all)
        act.addStretch(1)
        self.btn_off = QPushButton("关闭灯光")
        self.btn_off.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_off.clicked.connect(lambda: self._on_power(False))
        act.addWidget(self.btn_off)
        cl.addLayout(act)
        return center

    def _build_right(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("RightPanel")
        panel.setFixedWidth(306)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 14, 16, 14)
        pl.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 6, 0)
        il.setSpacing(6)

        il.addWidget(SectionTitle("亮度"))
        self.s_bright = SliderRow("整体亮度", self.cfg.get("brightness", 0.72))
        self.s_bright.value_changed.connect(self._on_brightness)
        il.addWidget(self.s_bright)

        il.addSpacing(4)
        il.addWidget(SectionTitle("动态"))
        self.s_speed = SliderRow("速度", (self.cfg.get("speed", 1.0) - 0.2) / 3.3)
        self.s_speed.set_formatter(lambda v: "%.2fx" % (0.2 + v * 3.3))
        self.s_speed.value_changed.connect(self._on_speed)
        il.addWidget(self.s_speed)

        self.s_size = SliderRow("效果尺寸", self.cfg.get("size", 0.4))
        self.s_size.value_changed.connect(self._on_size)
        il.addWidget(self.s_size)

        lab = QLabel("方向")
        lab.setStyleSheet("font-size:12px;color:%s;padding-top:4px;" % T.SUB)
        il.addWidget(lab)
        self.seg_dir = Segmented(["正向", "反向"], 0 if self.cfg.get("dir", 1) >= 0 else 1)
        self.seg_dir.changed.connect(lambda i: self.engine.set_param("dir", 1 if i == 0 else -1))
        il.addWidget(self.seg_dir)

        il.addSpacing(6)
        self.color_title = SectionTitle("颜色")
        il.addWidget(self.color_title)

        wheel_row = QHBoxLayout()
        wheel_row.setSpacing(8)

        self.box_a = QWidget()
        va = QVBoxLayout(self.box_a)
        va.setContentsMargins(0, 0, 0, 0)
        va.setSpacing(1)
        self.wheel_a = ColorWheel(tuple(self.cfg.get("c1", [0, 190, 255])), 118)
        self.wheel_a.color_changed.connect(lambda c: self.engine.set_color("c1", c))
        la = QLabel("主色")
        la.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        la.setStyleSheet("font-size:10px;color:%s;" % T.SUB)
        va.addWidget(self.wheel_a, 0, Qt.AlignmentFlag.AlignHCenter)
        va.addWidget(la)

        self.box_b = QWidget()
        vb = QVBoxLayout(self.box_b)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(1)
        self.wheel_b = ColorWheel(tuple(self.cfg.get("c2", [24, 8, 48])), 118)
        self.wheel_b.color_changed.connect(lambda c: self.engine.set_color("c2", c))
        lb = QLabel("副色")
        lb.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lb.setStyleSheet("font-size:10px;color:%s;" % T.SUB)
        vb.addWidget(self.wheel_b, 0, Qt.AlignmentFlag.AlignHCenter)
        vb.addWidget(lb)

        wheel_row.addStretch(1)
        wheel_row.addWidget(self.box_a)
        wheel_row.addWidget(self.box_b)
        wheel_row.addStretch(1)
        il.addLayout(wheel_row)

        self.pal_title = SectionTitle("调色板")
        il.addWidget(self.pal_title)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.swatches: Dict[str, Swatch] = {}
        for i, (pname, cols) in enumerate(COLORS.PALETTES.items()):
            sw = Swatch(pname, cols)
            sw.setToolTip(pname)
            sw.clicked.connect(lambda _=False, n=pname: self._select_palette(n))
            grid.addWidget(sw, i // 3, i % 3)
            self.swatches[pname] = sw
        il.addLayout(grid)

        il.addStretch(1)
        scroll.setWidget(inner)
        pl.addWidget(scroll, 1)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 8, 0, 0)
        btn = QPushButton("设置")
        btn.setObjectName("Ghost")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._open_settings)
        foot.addWidget(btn)
        foot.addStretch(1)
        ver = QLabel("v%s · 直连 + 风扇" % __version__)
        ver.setStyleSheet("font-size:10px;color:%s;" % T.DIM)
        foot.addWidget(ver)
        pl.addLayout(foot)
        return panel

    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(30)
        bar.setStyleSheet("background:%s;border-top:1px solid %s;" % (T.BG2, T.BORDER))
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(16)
        self.st_left = QLabel("就绪")
        self.st_left.setStyleSheet("font-size:11px;color:%s;" % T.SUB)
        lay.addWidget(self.st_left)
        lay.addStretch(1)
        self.st_stats = QLabel("")
        self.st_stats.setStyleSheet("font-size:11px;color:%s;font-family:Consolas,monospace;" % T.DIM)
        lay.addWidget(self.st_stats)
        return bar

    # ------------------------------------------------------------ 圆角 / 图标

    def _enable_round_corners(self) -> None:
        try:
            hwnd = int(self.winId())
            val = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), ctypes.c_int(33),
                ctypes.byref(val), ctypes.sizeof(val))
        except Exception:
            pass

    # ------------------------------------------------------------ 应用配置

    def _apply_config(self) -> None:
        c = self.cfg
        self.engine.set_effect(c.get("effect", "aurora"))
        self.engine.params["speed"] = float(c.get("speed", 1.0))
        self.engine.params["size"] = float(c.get("size", 0.4))
        self.engine.params["dir"] = int(c.get("dir", 1))
        self.engine.params["c1"] = tuple(c.get("c1", [0, 190, 255]))
        self.engine.params["c2"] = tuple(c.get("c2", [24, 8, 48]))
        self.engine.set_param("pal", c.get("pal", "极光"))
        self.engine.set_brightness(float(c.get("brightness", 0.72)))

        eid = c.get("effect", "aurora")
        if eid in self.effect_buttons:
            self.effect_buttons[eid].setChecked(True)
        self._sync_param_panel()
        self._select_palette(c.get("pal", "极光"), push=False)

    def _sync_param_panel(self) -> None:
        spec = FX.EFFECT_MAP.get(self.engine.effect_id)
        if spec is None:
            return
        mode = spec.color_mode
        self.effect_tag.setText(spec.name)
        show_a = mode in ("single", "dual")
        show_b = mode == "dual"
        show_pal = mode == "palette"
        self.color_title.setVisible(show_a)
        self.box_a.setVisible(show_a)
        self.box_b.setVisible(show_b)
        self.pal_title.setVisible(show_pal)
        for k, sw in self.swatches.items():
            sw.setVisible(show_pal)
        # 让布局重新收缩
        for w in (self.wheel_a, self.wheel_b):
            w.updateGeometry()

    # ------------------------------------------------------------ 设备

    def _scan_devices(self) -> None:
        self.channels = []
        self._clear_cards()

        cb = ColorfulBackend(int(self.cfg.get("led_count", 220)))
        self.backends["colorful"] = cb
        try:
            chans = cb.scan()
        except Exception:
            chans = []
        self.channels.extend(chans)

        if self.cfg.get("openrgb", True):
            ob = OpenRGBBackend()
            self.backends["openrgb"] = ob
            try:
                och = ob.scan()
            except Exception:
                och = []
            self.channels.extend(och)

        # 注册到引擎
        alive = set()
        for ch in self.channels:
            backend = self.backends.get(ch.backend_id)
            if backend is None:
                continue
            self.engine.register(ch, backend)
            alive.add(ch.key)
        self.engine.unregister_missing(alive)

        # 恢复关闭状态
        off = set(self.cfg.get("channels_off", []) or [])
        for k, st in self.engine.states.items():
            st.enabled = k not in off
        # 若所有通道都被禁用（配置残留 / 上次异常退出），自动全部恢复，
        # 否则用户打开软件会看到一片漆黑，以为程序坏了
        if self.engine.states and not any(s.enabled for s in self.engine.states.values()):
            for st in self.engine.states.values():
                st.enabled = True
            self.cfg["channels_off"] = []

        self._build_cards()
        self._update_status()
        self._preview_key = self._pick_preview()

    def _pick_preview(self) -> Optional[str]:
        for k, s in self.engine.states.items():
            if s.enabled:
                return k
        for k in self.engine.states:
            return k
        return None

    def _clear_cards(self) -> None:
        while self.dev_row.count():
            item = self.dev_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.cards.clear()

    def _build_cards(self) -> None:
        self._clear_cards()
        if not self.channels:
            empty = QFrame()
            empty.setObjectName("CardFlat")
            empty.setFixedHeight(66)
            lay = QVBoxLayout(empty)
            lay.setContentsMargins(16, 10, 16, 10)
            lab = QLabel("未检测到可控设备")
            lab.setStyleSheet("font-size:13px;font-weight:600;color:%s;" % T.WARN)
            sub = QLabel("确认主板 ARGB 已连接；如需控制显卡/内存请启动 OpenRGB 服务")
            sub.setStyleSheet("font-size:11px;color:%s;" % T.SUB)
            lay.addWidget(lab)
            lay.addWidget(sub)
            self.dev_row.addWidget(empty, 1)
            return

        for ch in self.channels:
            state = self.engine.states.get(ch.key)
            online = bool(state and state.last_ok)
            card = DeviceCard(ch.name, "%d 颗灯 · %s" % (ch.led_count, ch.device_name), ch.kind)
            card.set_online(True)
            card.set_sub(ch.note or ("%d 颗灯" % ch.led_count))
            if state is not None:
                card.switch.setChecked(state.enabled)
                card.toggled.connect(lambda on, key=ch.key: self._toggle_channel(key, on))
            self.cards[ch.key] = card
            self.dev_row.addWidget(card, 1)

    def _toggle_channel(self, key: str, on: bool) -> None:
        st = self.engine.states.get(key)
        if st is None:
            return
        st.enabled = on
        if not on:
            # 立即发送一帧黑色，避免停在上一帧
            self.engine.writer.submit(st.backend, st.channel, bytes(len(st.buf)))
        self._save_off_list()
        self._preview_key = self._pick_preview()

    def _enable_all(self) -> None:
        for k, st in self.engine.states.items():
            st.enabled = True
            card = self.cards.get(k)
            if card:
                card.switch.blockSignals(True)
                card.switch.setChecked(True)
                card.switch.blockSignals(False)
        self._save_off_list()
        self._preview_key = self._pick_preview()

    def _save_off_list(self) -> None:
        self.cfg["channels_off"] = [k for k, s in self.engine.states.items() if not s.enabled]

    # ------------------------------------------------------------ 交互

    def _select_effect(self, eid: str) -> None:
        self.engine.set_effect(eid)
        spec = FX.EFFECT_MAP.get(eid)
        if spec:
            self.s_speed.set_value((self.engine.params["speed"] - 0.2) / 3.3)
            self.s_size.set_value(self.engine.params["size"])
        b = self.effect_buttons.get(eid)
        if b:
            b.setChecked(True)
        self._sync_param_panel()
        self._apply_timer()

    def _select_palette(self, name: str, push: bool = True) -> None:
        if push:
            self.engine.set_param("pal", name)
        for n, sw in self.swatches.items():
            sw.setChecked(n == name)
        self._pal = name

    def _on_side_tab(self, i: int) -> None:
        self.center_stack.setCurrentIndex(i)
        self.right_stack.setCurrentIndex(i)
        self.side_stack.setCurrentIndex(i)
        if i == 1:
            self.fan_panel._init()
            self.fan_right.refresh_state()
            self.fan_side.refresh()
        else:
            for s in self.engine.states.values():
                s.dirty = True

    def _on_brightness(self, v: float) -> None:
        self.engine.set_brightness(v)

    def _on_speed(self, v: float) -> None:
        self.engine.set_param("speed", 0.2 + v * 3.3)

    def _on_size(self, v: float) -> None:
        self.engine.set_param("size", v)

    def _apply_preset(self, effect: str, color, bright: float,
                      pal: str, speed: float) -> None:
        self.engine.set_effect(effect)
        self.engine.set_color("c1", tuple(color))
        self.engine.set_param("pal", pal)
        self.engine.set_param("speed", speed)
        self.engine.set_brightness(bright)

        self.s_bright.set_value(bright)
        self.s_speed.set_value(max(0.0, min(1.0, (speed - 0.2) / 3.3)))
        self.s_size.set_value(self.engine.params.get("size", 0.4))
        self.wheel_a.set_color(tuple(color))
        self._select_palette(pal)
        b = self.effect_buttons.get(effect)
        if b:
            b.setChecked(True)
        self._sync_param_panel()
        self._apply_timer()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.values()
            auto_mode = int(vals.pop("autostart", 0))
            changed_leds = int(vals["led_count"]) != int(self.cfg.get("led_count", 220))
            self.cfg.update(vals)
            CFG.save(self.cfg)
            self._fps = int(vals["fps"])
            self._apply_timer()
            if changed_leds:
                self._rescan()
            for s in self.engine.states.values():
                s.dirty = True
            self._apply_autostart(auto_mode)

    def _apply_autostart(self, mode: int) -> None:
        try:
            if mode == 0:
                ok, msg = AS.disable_all()
            elif mode == 1:
                ok, msg = AS.enable_run()
            elif mode == 2:
                ok, msg = AS.enable_logon()
            else:
                ok, msg = AS.enable_boot()
        except Exception as exc:
            ok, msg = False, str(exc)
        if not ok:
            QMessageBox.warning(
                self, "开机启动设置失败",
                "这一项需要管理员权限，或者系统拒绝了操作。\n\n"
                "建议改用「登录时启动（推荐）」，那个不需要管理员。\n\n"
                "系统返回：%s" % (msg or "(无输出)"))
        else:
            self.st_left.setText("开机启动已更新：%s" % (msg or "成功"))

    def _stop_vendor(self) -> bool:
        return ColorfulBackend.stop_vendor_service()

    def _on_power(self, on: bool) -> None:
        self._power_on = on
        if getattr(self, "_tray_power", None) is not None:
            self._tray_power.setText("关闭灯光" if on else "开启灯光")
        self.titlebar.power.sync(on)
        if on:
            self.engine.paused = False
            for s in self.engine.states.values():
                s.dirty = True
        else:
            # 先推一帧纯黑再把渲染挂起，避免灯停在上一帧
            for s in self.engine.states.values():
                if s.enabled:
                    black = bytes(s.channel.led_count * 3)
                    self.engine.writer.submit(s.backend, s.channel, black)
            self.engine.paused = True
            # 预览也跟着熄掉，视觉上才一致
            key = self._preview_key
            if key and key in self.engine.states:
                st = self.engine.states[key]
                self.strip.set_frame(bytes(st.channel.led_count * 3), st.channel.led_count)
        self._apply_timer()

    # ------------------------------------------------------------ 每帧

    def _apply_timer(self) -> None:
        """按效果类型和窗口状态决定刷新间隔。

        静态色不需要 30fps，5fps 就够；熄灯后降到 2fps；
        窗口最小化时直接停表，占用归零。
        """
        timer = getattr(self, "_timer", None)
        if timer is None:
            return
        if getattr(self, "_minimized", False):
            if timer.isActive():
                timer.stop()
            return
        spec = FX.EFFECT_MAP.get(self.engine.effect_id)
        if self.engine.paused or not self.engine.states:
            target = 2
        elif spec is not None and spec.id == "static":
            target = 5
        else:
            target = int(self.cfg.get("fps", 30))
        target = max(2, min(120, target))
        interval = max(8, int(round(1000.0 / target)))
        if (not timer.isActive()) or timer.interval() != interval:
            timer.start(interval)

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if e.type() == QEvent.Type.WindowStateChange:
            self._minimized = self.isMinimized()
            self._apply_timer()

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = now - self._last
        self._last = now
        if dt <= 0:
            return
        frame = self.engine.tick(dt)

        # 界面预览按 20fps 更新，硬件仍按设定帧率推送，
        # 灯带的观感几乎没差别，但绘制开销能省下三分之一。
        self._pv_acc += dt
        if self._pv_acc >= 0.05:
            self._pv_acc = 0.0
            if self.center_stack.currentIndex() == 0 and self.isVisible():
                key = self._preview_key
                if key and key in frame:
                    st = self.engine.states.get(key)
                    if st is not None:
                        self.strip.set_frame(frame[key], st.channel.led_count)

        self._stat_acc += dt
        if self._stat_acc >= 0.8:
            self._stat_acc = 0.0
            self._update_status()

    def _update_status(self) -> None:
        if psutil is not None:
            try:
                if self._proc is None:
                    self._proc = psutil.Process()
                    self._proc.cpu_percent(None)
                self._cpu = self._proc.cpu_percent(None)
                self._mem = self._proc.memory_info().rss / (1024 * 1024)
            except Exception:
                pass

        # 风扇模块读到的 CPU 温度直接喂给灯效引擎，「温度律动」用的就是这个值
        try:
            self.engine.temp = self.fan_panel.bridge.cpu_temp
        except Exception:
            self.engine.temp = None

        cs = getattr(self, "center_stack", None)
        if cs is not None and cs.currentIndex() == 1:
            self._update_fan_status()
            return
        alive = sum(1 for s in self.engine.states.values() if s.enabled)
        total = len(self.engine.states)
        cb = self.backends.get("colorful")
        ok = bool(getattr(cb, "ready", False))

        self.titlebar.status_dot.set_state(ok or total > 0)
        if total == 0:
            txt = "未连接硬件"
        elif ok:
            txt = "主板已直连"
        else:
            txt = "外部设备 %d 台" % total
        if not self._power_on:
            txt = "输出已关闭"
        self.titlebar.status_text.setText(txt)

        self.st_left.setText(
            "七彩虹 ARGB 直连 · %d 个通道启用" % alive if ok else "仅预览模式 · %d 个通道" % alive
        )

        spec = FX.EFFECT_MAP.get(self.engine.effect_id)
        self.effect_tag.setText(spec.name if spec else "")
        if self._preview_key and self._preview_key in self.engine.states:
            ch = self.engine.states[self._preview_key].channel
            self.strip.set_label(ch.name, "%d 颗灯 · %s" % (ch.led_count, ch.note))
            self.strip.set_offline(False)
            self.led_tag.setText("%d 颗灯珠" % ch.led_count)
        else:
            self.strip.set_label("预览", "当前没有可控制的设备")
            self.strip.set_offline(True)
            self.led_tag.setText("")

        self.st_stats.setText(
            "%.0f FPS   %.2f ms   CPU %.0f%%   %d MB"
            % (self.engine.fps, self.engine.render_ms, self._cpu, int(self._mem))
        )

    def _update_fan_status(self) -> None:
        b = self.fan_panel.bridge
        n = len(b.fans)
        act = len([f for f in b.fans if f.rpm > 1])
        self.titlebar.status_dot.set_state(n > 0)
        self.titlebar.status_text.setText(
            "风扇 %d 通道" % n if n else "风扇未就绪")
        self.st_left.setText(
            "风扇控制 · Nuvoton NCT6799D · %d 个在转" % act if n else "风扇控制未初始化")
        cpu = ("%.0f°C" % b.cpu_temp) if b.cpu_temp is not None else "--"
        self.st_stats.setText(
            "CPU %s   传感器 %.1f ms   CPU占用 %.0f%%   %d MB"
            % (cpu, b.update_ms, self._cpu, int(self._mem)))

    # ------------------------------------------------------------ 托盘

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self.windowIcon(), self)
        tray.setToolTip("Aurora ARGB Studio")

        menu = QMenu()
        act_show = menu.addAction("显示主窗口")
        act_show.triggered.connect(self._restore_from_tray)
        menu.addSeparator()
        self._tray_power = menu.addAction("关闭灯光")
        self._tray_power.triggered.connect(lambda: self._on_power(not self._power_on))
        act_fan = menu.addAction("风扇控制")
        act_fan.triggered.connect(self._show_fan_tab)
        menu.addSeparator()
        act_quit = menu.addAction("退出")
        act_quit.triggered.connect(self._quit_app)

        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray = tray

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._last = time.perf_counter()
        self._minimized = False
        self._apply_timer()

    def _show_fan_tab(self) -> None:
        self._restore_from_tray()
        if self.side_tab.index() != 1:
            self.side_tab.set_index(1)
            self._on_side_tab(1)

    def _quit_app(self) -> None:
        self._really_quit = True
        if self._tray is not None:
            self._tray.hide()
        self.close()
        # quitOnLastWindowClosed 已关掉，这里必须显式退出事件循环
        QApplication.quit()

    def _save_state(self) -> None:
        self.cfg.update({
            "effect": self.engine.effect_id,
            "brightness": self.engine.brightness,
            "speed": self.engine.params.get("speed", 1.0),
            "size": self.engine.params.get("size", 0.4),
            "dir": self.engine.params.get("dir", 1),
            "c1": list(self.engine.params.get("c1", (0, 190, 255))),
            "c2": list(self.engine.params.get("c2", (24, 8, 48))),
            "pal": self.engine.params.get("pal", "极光"),
            "window": [self.width(), self.height()],
            "channels_off": [k for k, s in self.engine.states.items() if not s.enabled],
        })
        CFG.save(self.cfg)

    # ------------------------------------------------------------ 生命周期

    def _rescan(self) -> None:
        for b in self.backends.values():
            try:
                b.close()
            except Exception:
                pass
        self.backends.clear()
        self.engine.clear()
        self._scan_devices()
        for s in self.engine.states.values():
            s.dirty = True

    def closeEvent(self, e) -> None:
        # 点右上角 × 只是收进托盘：灯效和风扇要继续跑，
        # 真正退出走托盘右键菜单里的「退出」。
        if not self._really_quit and self._tray is not None:
            e.ignore()
            self._save_state()
            self.hide()
            if not self.cfg.get("tray_hint"):
                self._tray.showMessage(
                    "Aurora ARGB",
                    "窗口已收进托盘，灯效和风扇控制继续运行。\n"
                    "双击图标恢复窗口，右键菜单里有退出。",
                    QSystemTrayIcon.MessageIcon.Information, 5000)
                self.cfg["tray_hint"] = True
                CFG.save(self.cfg)
            return

        self._save_state()
        self._timer.stop()
        try:
            self.fan_panel.shutdown()
        except Exception:
            pass
        self.engine.shutdown()
        for b in self.backends.values():
            try:
                b.close()
            except Exception:
                pass
        super().closeEvent(e)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        for g in self.findChildren(QSizeGrip):
            g.move(self.width() - 18, self.height() - 18)
            g.raise_()


# ---------------------------------------------------------------- 设置对话框

def _dark_titlebar(widget: QWidget) -> None:
    """让 Windows 原生标题栏跟着变深色，避免深色界面顶一条白条。"""
    try:
        hwnd = int(widget.winId())
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), ctypes.c_int(20),
            ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


def _elevate_and_stop_vendor() -> None:
    """以管理员身份重启自己，新进程启动时自动停掉 iGame Center 服务。"""
    try:
        if getattr(sys, "frozen", False):
            target = sys.executable
            params = "--stop-vendor"
        else:
            target = sys.executable
            params = '"%s" --stop-vendor' % os.path.abspath(sys.argv[0])
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", target, params, None, 1)
    except Exception:
        pass
    QApplication.quit()


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.setFixedWidth(452)
        self.setStyleSheet("QDialog{background:%s;}" % T.BG2)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(12)

        title = QLabel("设置")
        title.setStyleSheet("font-size:18px;font-weight:700;color:%s;" % T.TEXT)
        lay.addWidget(title)

        # 灯珠数量
        r1 = QHBoxLayout()
        l1 = QLabel("主板灯珠数量")
        l1.setStyleSheet("font-size:13px;color:%s;" % T.TEXT)
        self.spin = QSpinBox()
        self.spin.setRange(30, 520)
        self.spin.setSingleStep(10)
        self.spin.setValue(int(cfg.get("led_count", 220)))
        r1.addWidget(l1, 1)
        r1.addWidget(self.spin)
        lay.addLayout(r1)
        h1 = QLabel("不确定就保持 220。调大不会损坏硬件，只是多发的数据被忽略；\n"
                    "如果只有一部分灯珠出效果，可以试着调大这个值。")
        h1.setStyleSheet("font-size:11px;color:%s;line-height:150%%;" % T.SUB)
        lay.addWidget(h1)

        # 刷新率
        r2 = QHBoxLayout()
        l2 = QLabel("渲染刷新率")
        l2.setStyleSheet("font-size:13px;color:%s;" % T.TEXT)
        self.fps_label = QLabel("%d fps" % int(cfg.get("fps", 30)))
        self.fps_label.setStyleSheet("font-size:13px;font-weight:700;color:%s;" % T.ACCENT)
        r2.addWidget(l2, 1)
        r2.addWidget(self.fps_label)
        lay.addLayout(r2)

        self.fps_slider = QSlider(Qt.Orientation.Horizontal)
        self.fps_slider.setRange(10, 120)
        self.fps_slider.setSingleStep(5)
        self.fps_slider.setPageStep(10)
        self.fps_slider.setValue(int(cfg.get("fps", 30)))
        self.fps_slider.valueChanged.connect(self._on_fps)
        lay.addWidget(self.fps_slider)

        quick = QHBoxLayout()
        quick.setSpacing(6)
        for v in (20, 30, 60, 90, 120):
            qb = QPushButton(str(v))
            qb.setObjectName("Ghost")
            qb.setFixedWidth(52)
            qb.setCursor(Qt.CursorShape.PointingHandCursor)
            qb.clicked.connect(lambda _=False, x=v: self.fps_slider.setValue(x))
            quick.addWidget(qb)
        quick.addStretch(1)
        lay.addLayout(quick)

        h2 = QLabel("拖动即时生效。播放动画时 30 已经够顺滑；静态颜色会自动降到 5 fps 省电，"
                    "窗口最小化时完全停帧。")
        h2.setStyleSheet("font-size:11px;color:%s;" % T.SUB)
        h2.setWordWrap(True)
        lay.addWidget(h2)

        # OpenRGB
        self.chk = QCheckBox("同时连接 OpenRGB（用于显卡、内存灯条、其它品牌主板）")
        self.chk.setChecked(bool(cfg.get("openrgb", True)))
        lay.addWidget(self.chk)

        orow = QHBoxLayout()
        self.or_state = QLabel("")
        self.or_state.setStyleSheet("font-size:11px;color:%s;" % T.SUB)
        orow.addWidget(self.or_state, 1)
        self.btn_openrgb = QPushButton("启动 OpenRGB 服务")
        self.btn_openrgb.setObjectName("Ghost")
        self.btn_openrgb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_openrgb.clicked.connect(self._launch_openrgb)
        orow.addWidget(self.btn_openrgb)
        lay.addLayout(orow)
        self._refresh_openrgb()

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:%s;" % T.BORDER)
        lay.addWidget(line)

        # 接管按钮
        r3 = QHBoxLayout()
        l3 = QLabel("iGame Center 服务")
        l3.setStyleSheet("font-size:13px;color:%s;" % T.TEXT)
        self.svc_state = QLabel("检测中…")
        self.svc_state.setStyleSheet("font-size:11px;color:%s;" % T.SUB)
        r3.addWidget(l3)
        r3.addWidget(self.svc_state, 1, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(r3)

        self.btn_stop = QPushButton("停止厂商服务（需管理员）")
        self.btn_stop.setObjectName("Ghost")
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.clicked.connect(self._stop_svc)
        lay.addWidget(self.btn_stop)

        h3 = QLabel("厂商服务会持续抢占 HID 设备。停止它之后本程序可以独占控制，\n"
                    "重启电脑后它会自动恢复，不会破坏系统。")
        h3.setStyleSheet("font-size:11px;color:%s;line-height:150%%;" % T.SUB)
        lay.addWidget(h3)

        lay.addSpacing(10)
        diag = QPushButton("硬件诊断（芯片 / 风扇 / 驱动）")
        diag.setObjectName("Ghost")
        diag.setCursor(Qt.CursorShape.PointingHandCursor)
        diag.clicked.connect(lambda: DiagDialog(self).exec())
        lay.addWidget(diag)

        # 开机启动
        line2 = QFrame()
        line2.setFixedHeight(1)
        line2.setStyleSheet("background:%s;" % T.BORDER)
        lay.addWidget(line2)

        r4 = QHBoxLayout()
        l4 = QLabel("开机启动")
        l4.setStyleSheet("font-size:13px;color:%s;" % T.TEXT)
        self.autostart = QComboBox()
        self.autostart.addItems([
            "不自动启动",
            "登录时启动（推荐）",
            "登录时启动（最高权限）",
            "开机即启动（登录前）",
        ])
        try:
            st = AS.status()
            if st.get("boot"):
                self.autostart.setCurrentIndex(3)
            elif st.get("logon"):
                self.autostart.setCurrentIndex(2)
            elif st.get("run"):
                self.autostart.setCurrentIndex(1)
            else:
                self.autostart.setCurrentIndex(0)
        except Exception:
            self.autostart.setCurrentIndex(0)
        r4.addWidget(l4, 1)
        r4.addWidget(self.autostart)
        lay.addLayout(r4)

        self.autostart_hint = QLabel("")
        self.autostart_hint.setWordWrap(True)
        self.autostart_hint.setStyleSheet("font-size:11px;color:%s;line-height:150%%;" % T.SUB)
        lay.addWidget(self.autostart_hint)
        self.autostart.currentIndexChanged.connect(self._on_autostart_changed)
        self._on_autostart_changed(self.autostart.currentIndex())

        lay.addSpacing(6)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("保存并应用")
        ok.setObjectName("Primary")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

        self._refresh_svc()
        _dark_titlebar(self)

    def _refresh_openrgb(self) -> None:
        exe = OpenRGBBackend.find_executable()
        probe = OpenRGBBackend()
        connected = False
        try:
            connected = probe.connect()
        finally:
            probe.close()
        if connected:
            self.or_state.setText("服务已运行 · SDK 6742")
            self.or_state.setStyleSheet("font-size:11px;color:%s;" % T.OK)
            self.btn_openrgb.setText("已连接")
            self.btn_openrgb.setEnabled(False)
        elif exe:
            self.or_state.setText("已安装，服务未启动")
            self.or_state.setStyleSheet("font-size:11px;color:%s;" % T.WARN)
            self.btn_openrgb.setText("启动 OpenRGB 服务")
            self.btn_openrgb.setEnabled(True)
        else:
            self.or_state.setText("未安装（可选）")
            self.or_state.setStyleSheet("font-size:11px;color:%s;" % T.DIM)
            self.btn_openrgb.setText("了解 OpenRGB")
            self.btn_openrgb.setEnabled(True)

    def _launch_openrgb(self) -> None:
        if OpenRGBBackend.find_executable():
            ok = OpenRGBBackend.launch_with_server()
            self.or_state.setText("正在启动…" if ok else "启动失败，请手动运行")
            self.or_state.setStyleSheet("font-size:11px;color:%s;" % T.SUB)
            QTimer.singleShot(2600, self._refresh_openrgb)
        else:
            import webbrowser
            try:
                webbrowser.open("https://openrgb.org/")
            except Exception:
                pass
            self.or_state.setText("已打开下载页")
            self.or_state.setStyleSheet("font-size:11px;color:%s;" % T.SUB)

    def _refresh_svc(self) -> None:
        try:
            run = ColorfulBackend.vendor_service_running()
        except Exception:
            run = False
        if run:
            self.svc_state.setText("运行中 · 可能抢占设备")
            self.svc_state.setStyleSheet("font-size:11px;color:%s;" % T.WARN)
            self.btn_stop.setEnabled(True)
            self.btn_stop.setText("停止厂商服务（需管理员）")
        else:
            self.svc_state.setText("未运行")
            self.svc_state.setStyleSheet("font-size:11px;color:%s;" % T.OK)
            self.btn_stop.setEnabled(False)
            self.btn_stop.setText("厂商服务未运行")

    def _stop_svc(self) -> None:
        ok = ColorfulBackend.stop_vendor_service()
        self._refresh_svc()
        if ok:
            self.svc_state.setText("已停止 · 本程序可独占设备")
            self.svc_state.setStyleSheet("font-size:11px;color:%s;" % T.OK)
            self.btn_stop.setText("已停止（重启电脑后自动恢复）")
            self.btn_stop.setEnabled(False)
        else:
            # 普通权限停不掉服务，提权重启自己，新进程启动后会自动停服务
            self.btn_stop.setText("正在请求管理员权限…")
            self.btn_stop.setEnabled(False)
            self.reject()
            _elevate_and_stop_vendor()

    def _on_autostart_changed(self, idx: int) -> None:
        hints = {
            0: "关闭自启。已经在系统里留过任务或注册表项的，保存时会一并清掉。",
            1: "写注册表 Run 项，登录进桌面后自动启动。不需要管理员，最稳，推荐用这个。",
            2: "用计划任务以「最高权限」在登录后启动。需要管理员权限才能创建。",
            3: "用计划任务以 SYSTEM 身份在开机时拉起无界面守护，登录界面时灯就在跑；"
               "登录后主界面接管、守护退场。需要管理员权限。",
        }
        self.autostart_hint.setText(hints.get(idx, ""))

    def _on_fps(self, v: int) -> None:
        self.fps_label.setText("%d fps" % v)

    def values(self) -> dict:
        return {
            "led_count": self.spin.value(),
            "fps": int(self.fps_slider.value()),
            "openrgb": self.chk.isChecked(),
            "autostart": self.autostart.currentIndex(),
        }


class DiagDialog(QDialog):
    """硬件诊断：把驱动、芯片、风扇、温度、冲突状态一次性摊开。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("硬件诊断")
        self.setModal(True)
        self.setFixedSize(600, 680)
        self.setStyleSheet("QDialog{background:%s;}" % T.BG2)
        _dark_titlebar(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)

        title = QLabel("硬件诊断")
        title.setStyleSheet("font-size:17px;font-weight:700;color:%s;" % T.TEXT)
        lay.addWidget(title)

        sub = QLabel("排障用。风扇读不到时先看这里哪一项是红的。")
        sub.setStyleSheet("font-size:11px;color:%s;" % T.SUB)
        lay.addWidget(sub)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet(
            "QTextEdit{background:%s;border:1px solid %s;border-radius:10px;"
            "color:%s;font-family:Consolas,monospace;font-size:12px;padding:12px;}"
            % (T.PANEL, T.BORDER, T.TEXT))
        lay.addWidget(self.text, 1)

        row = QHBoxLayout()
        rb = QPushButton("重新检测")
        rb.setObjectName("Ghost")
        rb.setCursor(Qt.CursorShape.PointingHandCursor)
        rb.clicked.connect(self._reload)
        row.addWidget(rb)
        row.addStretch(1)
        cb = QPushButton("关闭")
        cb.setObjectName("Primary")
        cb.setCursor(Qt.CursorShape.PointingHandCursor)
        cb.clicked.connect(self.accept)
        row.addWidget(cb)
        lay.addLayout(row)

        self._reload()

    def _reload(self) -> None:
        try:
            self.text.setPlainText(self._format(FAN.diagnose()))
        except Exception as exc:
            self.text.setPlainText("诊断失败：%s" % exc)

    @staticmethod
    def _format(i: dict) -> str:
        def mark(ok: bool) -> str:
            return "OK " if ok else "!! "

        L = []
        L.append("=== 权限与驱动 ===")
        L.append("  %s管理员权限          %s" % (mark(bool(i["admin"])),
                                              "已获得" if i["admin"] else "未获得（风扇不可用）"))
        L.append("  %sPawnIO 驱动          %s" % (mark(bool(i["pawnio"])),
                                              "运行中" if i["pawnio"] else "未运行"))
        L.append("  .NET 运行时          %s" % i["dotnet"])
        L.append("")

        L.append("=== 运行时文件 (third_party/lhm) ===")
        for name, ok, size in i["dlls"]:
            L.append("  %s%-32s %s" % (mark(ok), name,
                                       ("%.2f MB" % (size / 1048576.0)) if ok else "缺失"))
        L.append("")

        L.append("=== 硬件 ===")
        L.append("  主板                 %s" % (i["board"] or "(未读取)"))
        L.append("  Super I/O 芯片       %s" % (i["chip"] or "(未读取)"))
        if i["lhm_err"]:
            L.append("  错误                 %s" % i["lhm_err"])
        L.append("")

        fans = i["fans"]
        L.append("=== 风扇通道 (%d) ===" % len(fans))
        if fans:
            for name, fid, pwm, rpm in fans:
                L.append("  %-8s %5.0f%%  %7.0f RPM   %s" % (name, pwm, rpm, fid))
        else:
            L.append("  (无数据)")
        L.append("")

        temps = i["temps"]
        L.append("=== 温度传感器 (%d 个有效) ===" % len(temps))
        for name, val in temps[:10]:
            L.append("  %-24s %5.1f C" % (name[:24], val))
        L.append("")

        L.append("=== 冲突检测 ===")
        fc = i["fancontrol"]
        L.append("  %sFanControl           %s" % (mark(fc is None),
                                              "未运行" if fc is None else "运行中 PID %d" % fc))
        L.append("")
        L.append("传感器单次刷新 %.1f ms" % i["update_ms"])
        return "\n".join(L)


# ---------------------------------------------------------------- 场景预设

PRESETS = [
    ("静夜", "冷蓝低亮，睡前不刺眼", "static", (18, 52, 96), 0.26, "冰霜", 0.6),
    ("极光", "流动的青紫光带", "aurora", (0, 214, 255), 0.78, "极光", 1.0),
    ("烈焰", "底部窜起的火焰", "fire", (255, 96, 16), 0.85, "火焰", 1.4),
    ("赛博", "霓虹光点掠过", "comet", (255, 20, 140), 0.82, "赛博", 1.8),
]


# ---------------------------------------------------------------- 图标

def _make_icon(size: int = 64) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    c = size / 2.0
    grad = QRadialGradient(c, c, c)
    grad.setColorAt(0.0, QColor(140, 235, 255))
    grad.setColorAt(0.45, QColor(61, 220, 255))
    grad.setColorAt(0.8, QColor(139, 92, 246))
    grad.setColorAt(1.0, QColor(80, 40, 160))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(QPointF(c, c), c * 0.92, c * 0.92)
    p.setPen(QPen(QColor(6, 14, 24), size * 0.075))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(c * 0.30, c * 0.30, c * 1.40, c * 1.40), 60 * 16, 250 * 16)
    p.drawLine(QPointF(c, c - size * 0.30), QPointF(c, c + size * 0.30))
    p.end()
    return QIcon(pm)
