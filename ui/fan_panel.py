"""风扇控制界面：温度总览 + 每个通道的 PWM 控制。"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from core import fans as FAN

from . import theme as T


class Bar(QWidget):
    """细长的水平进度条，用来显示 PWM 占空比。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(6)
        self._v = 0.0
        self._c1 = QColor(T.ACCENT)
        self._c2 = QColor(T.ACCENT2)

    def set_value(self, v: float) -> None:
        v = max(0.0, min(100.0, v))
        if abs(v - self._v) > 0.4:
            self._v = v
            self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.PANEL3))
        p.drawRoundedRect(r, 3, 3)
        if self._v > 0:
            w = max(6.0, r.width() * self._v / 100.0)
            g = QLinearGradient(0, 0, r.width(), 0)
            g.setColorAt(0.0, self._c1)
            g.setColorAt(1.0, self._c2)
            clip = QPainterPath()
            clip.addRoundedRect(r, 3, 3)
            p.setClipPath(clip)
            p.fillRect(QRectF(0, 0, w, r.height()), g)


class FanCard(QFrame):
    """单个风扇通道卡片。"""

    pwm_changed = Signal(str, float)
    restore_clicked = Signal(str)

    def __init__(self, fan: FAN.FanChannel, locked: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("CardFlat")
        self.setMinimumHeight(104)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.fan_id = fan.id
        self._locked = locked
        self._fan = fan

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 13, 16, 13)
        lay.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.name = QLabel(fan.name)
        self.name.setStyleSheet("font-size:13px;font-weight:600;color:%s;" % T.TEXT)
        top.addWidget(self.name)
        self.badge = QLabel("")
        self.badge.setStyleSheet("font-size:10px;color:%s;" % T.DIM)
        top.addWidget(self.badge)
        top.addStretch(1)
        self.rpm = QLabel("0 RPM")
        self.rpm.setStyleSheet("font-size:13px;font-weight:700;color:%s;font-family:Consolas;" % T.ACCENT)
        top.addWidget(self.rpm)
        lay.addLayout(top)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(20, 100)
        self.slider.setValue(int(fan.pwm))
        self.slider.setEnabled(not locked)
        self.slider.valueChanged.connect(self._on_slide)
        row.addWidget(self.slider, 1)
        self.pct = QLabel("%d%%" % int(fan.pwm))
        self.pct.setFixedWidth(42)
        self.pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.pct.setStyleSheet("font-size:12px;font-weight:600;color:%s;font-family:Consolas;" % T.TEXT)
        row.addWidget(self.pct)
        lay.addLayout(row)

        self.update_fan(fan)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self.slider.setEnabled(not locked)

    def _on_slide(self, v: int) -> None:
        self.pct.setText("%d%%" % v)
        if not self._locked:
            self.pwm_changed.emit(self.fan_id, float(v))

    def update_fan(self, fan: FAN.FanChannel) -> None:
        self._fan = fan
        self.rpm.setText("%d RPM" % int(round(fan.rpm)))
        if fan.rpm < 1:
            self.rpm.setStyleSheet("font-size:13px;font-weight:700;color:%s;font-family:Consolas;" % T.DIM)
            self.badge.setText("未接风扇")
        else:
            self.rpm.setStyleSheet("font-size:13px;font-weight:700;color:%s;font-family:Consolas;" % T.ACCENT)
            self.badge.setText("")
        if not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(int(round(fan.pwm)))
            self.slider.blockSignals(False)
            self.pct.setText("%d%%" % int(round(fan.pwm)))


class FanPanel(QWidget):
    """中间区域：温度总览 + 风扇卡片网格。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.bridge = FAN.instance()
        self.cards: Dict[str, FanCard] = {}
        self._inited = False
        self._fancontrol_pid: Optional[int] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 14)
        root.setSpacing(12)

        head = QHBoxLayout()
        t = QLabel("风扇与温度")
        t.setStyleSheet("font-size:20px;font-weight:700;color:%s;" % T.TEXT)
        head.addWidget(t)
        self.mode_tag = QLabel("")
        self.mode_tag.setStyleSheet(
            "font-size:11px;color:%s;background:%s;border:1px solid %s;"
            "border-radius:9px;padding:3px 10px;" % (T.WARN, T.PANEL2, T.BORDER))
        head.addWidget(self.mode_tag)
        head.addStretch(1)
        self.btn_admin = QPushButton("以管理员身份重启")
        self.btn_admin.setObjectName("Primary")
        self.btn_admin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_admin.clicked.connect(self._elevate)
        self.btn_admin.setVisible(False)
        head.addWidget(self.btn_admin)
        self.btn_takeover = QPushButton("接管风扇控制")
        self.btn_takeover.setObjectName("Ghost")
        self.btn_takeover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_takeover.clicked.connect(self._takeover)
        head.addWidget(self.btn_takeover)
        root.addLayout(head)

        # 状态横幅
        self.banner = QFrame()
        self.banner.setObjectName("CardFlat")
        self.banner.setVisible(False)
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(16, 10, 16, 10)
        bl.setSpacing(10)
        self.banner_text = QLabel("")
        self.banner_text.setStyleSheet("font-size:12px;color:%s;" % T.WARN)
        self.banner_text.setWordWrap(True)
        bl.addWidget(self.banner_text, 1)
        root.addWidget(self.banner)

        # 温度总览
        self.temp_card = QFrame()
        self.temp_card.setObjectName("CardFlat")
        self.temp_card.setFixedHeight(96)
        tl = QHBoxLayout(self.temp_card)
        tl.setContentsMargins(20, 12, 20, 12)
        tl.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(0)
        lab = QLabel("CPU 温度")
        lab.setStyleSheet("font-size:11px;color:%s;letter-spacing:1px;" % T.DIM)
        left.addWidget(lab)
        self.cpu_temp = QLabel("--")
        self.cpu_temp.setStyleSheet(
            "font-size:34px;font-weight:800;color:%s;font-family:Consolas;" % T.ACCENT)
        left.addWidget(self.cpu_temp)
        tl.addLayout(left)

        self.temp_list = QLabel("")
        self.temp_list.setStyleSheet("font-size:11px;color:%s;font-family:Consolas;" % T.SUB)
        self.temp_list.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        tl.addWidget(self.temp_list, 1)
        root.addWidget(self.temp_card)

        # 滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(inner)
        self.grid.setContentsMargins(0, 0, 6, 0)
        self.grid.setSpacing(10)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        self.hint = QLabel("正在初始化硬件监控…")
        self.hint.setStyleSheet("font-size:11px;color:%s;" % T.DIM)
        root.addWidget(self.hint)

        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self.companion = None       # 侧栏的 FanSide，用于同步温度列表
        QTimer.singleShot(600, self._init)

    # ------------------------------------------------------------ 初始化

    def _init(self) -> None:
        if self._inited:
            return
        if not FAN.is_admin():
            self._inited = True
            self.banner.setVisible(True)
            self.banner_text.setText(
                "读取风扇与温度需要管理员权限（要访问主板 Super I/O 芯片）。"
                "点右上角「以管理员身份重启」，在 UAC 弹窗里选「是」即可。")
            self.btn_admin.setVisible(True)
            self.btn_takeover.setVisible(False)
            self.hint.setText("未提权，硬件监控未启动")
            return
        err = self.bridge.open()
        self._inited = True
        self._fancontrol_pid = FAN.fancontrol_running()
        if err:
            self.hint.setText("无法初始化硬件监控：%s" % err)
            self._rebuild()
            return
        self._apply_lock_state()
        self._refresh_ui()

    def _apply_lock_state(self) -> None:
        locked = self._fancontrol_pid is not None
        for c in self.cards.values():
            c.set_locked(locked)

    # ------------------------------------------------------------ 轮询

    def _poll(self) -> None:
        if not self.isVisible():
            return
        if not self._inited:
            return
        if not self.bridge.available:
            self._init()
            return
        self.bridge.refresh()
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        b = self.bridge
        if not b.fans and not self.cards:
            self._rebuild()
            if not b.fans:
                self.hint.setText("没有检测到可控风扇通道")
                return

        if len(b.fans) != len(self.cards):
            self._rebuild()

        for f in b.fans:
            card = self.cards.get(f.id)
            if card is not None:
                card.update_fan(f)

        if b.cpu_temp is not None:
            self.cpu_temp.setText("%.0f°C" % b.cpu_temp)
            hot = b.cpu_temp >= 85
            col = T.ERR if hot else (T.WARN if b.cpu_temp >= 70 else T.ACCENT)
            self.cpu_temp.setStyleSheet(
                "font-size:34px;font-weight:800;color:%s;font-family:Consolas;" % col)
        else:
            self.cpu_temp.setText("--")

        valid = [t for t in b.temps if 0 < t.value < 110][:6]
        lines = []
        for t in valid:
            if "Tctl" in t.name or "Core" in t.name:
                continue
            lines.append("%-22s %5.1f°C" % (t.name[:22], t.value))
        self.temp_list.setText("\n".join(lines[:4]))

        self.mode_tag.setText("FanControl 已接管" if self._fancontrol_pid else "本程序控制")
        self.mode_tag.setStyleSheet(
            "font-size:11px;color:%s;background:%s;border:1px solid %s;"
            "border-radius:9px;padding:3px 10px;"
            % ((T.WARN if self._fancontrol_pid else T.OK), T.PANEL2, T.BORDER))

        self.banner.setVisible(self._fancontrol_pid is not None)
        if self._fancontrol_pid is not None:
            self.banner_text.setText(
                "FanControl 正在管理这些风扇，手动调节会被它每秒覆盖。"
                "想用本程序调速，点右上角「接管风扇控制」（会结束 FanControl 进程）。")
            self.btn_takeover.setVisible(True)
        else:
            self.btn_takeover.setVisible(False)

        self.hint.setText("传感器刷新 %d 项 · %.1f ms/次" % (len(b.fans), b.update_ms))
        if self.companion is not None:
            try:
                self.companion.refresh()
            except Exception:
                pass

    def _rebuild(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.cards.clear()
        if not self.bridge.fans:
            return
        cols = 2 if len(self.bridge.fans) > 3 else 1
        locked = self._fancontrol_pid is not None
        for i, f in enumerate(self.bridge.fans):
            card = FanCard(f, locked=locked)
            card.pwm_changed.connect(self._on_pwm)
            self.cards[f.id] = card
            self.grid.addWidget(card, i // cols, i % cols)

    def _on_pwm(self, fan_id: str, pct: float) -> None:
        if self._fancontrol_pid is not None:
            return
        ok = self.bridge.set_pwm(fan_id, pct)
        if not ok:
            self.hint.setText("写入失败：该通道可能被其它程序占用")

    # ------------------------------------------------------------ 接管

    def _elevate(self) -> None:
        """以管理员身份重启自己（读 Super I/O 必需）。"""
        import ctypes
        import os
        import sys
        try:
            target = sys.executable
            params = "" if getattr(sys, "frozen", False) else '"%s"' % os.path.abspath(sys.argv[0])
            r = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", target, params, None, 1)
            if r > 32:
                from PySide6.QtWidgets import QApplication
                QApplication.quit()
            else:
                self.hint.setText("提权被取消，风扇控制不可用")
        except Exception as exc:
            self.hint.setText("提权失败：%s" % exc)

    def _takeover(self) -> None:
        pid = FAN.fancontrol_running()
        if pid is None:
            self._fancontrol_pid = None
            self._apply_lock_state()
            self._refresh_ui()
            return
        try:
            import psutil
            p = psutil.Process(pid)
            p.terminate()
            try:
                p.wait(timeout=3)
            except Exception:
                p.kill()
        except Exception as exc:
            self.hint.setText("结束 FanControl 失败：%s" % exc)
            return
        self._fancontrol_pid = None
        self._apply_lock_state()
        self._refresh_ui()

    def shutdown(self) -> None:
        self._timer.stop()
        try:
            self.bridge.close()
        except Exception:
            pass


class FanSide(QWidget):
    """侧栏的风扇视图：温度列表 + 说明。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.bridge = FAN.instance()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 8, 2)
        lay.setSpacing(6)

        h = QLabel("温度传感器")
        h.setStyleSheet("font-size:10px;font-weight:700;color:%s;letter-spacing:1.2px;" % T.DIM)
        lay.addWidget(h)

        self.list = QLabel("正在读取…")
        self.list.setWordWrap(True)
        self.list.setStyleSheet(
            "font-size:11px;color:%s;font-family:Consolas;line-height:160%%;" % T.SUB)
        lay.addWidget(self.list)

        lay.addSpacing(10)
        h2 = QLabel("说明")
        h2.setStyleSheet("font-size:10px;font-weight:700;color:%s;letter-spacing:1.2px;" % T.DIM)
        lay.addWidget(h2)
        note = QLabel(
            "风扇由主板 Nuvoton 芯片控制，"
            "通过 LibreHardwareMonitor 直接读写，不依赖 BIOS 设置。\n\n"
            "PWM 下限锁在 20%，避免风扇停转。\n\n"
            "关闭页面后停止轮询，不会持续占用。")
        note.setWordWrap(True)
        note.setStyleSheet("font-size:11px;color:%s;line-height:150%%;" % T.DIM)
        lay.addWidget(note)
        lay.addStretch(1)

    def refresh(self) -> None:
        b = self.bridge
        if not b.available:
            self.list.setText("硬件监控未初始化")
            return
        rows = ["%-18s %5s" % ("传感器", "温度")]
        for t in b.temps:
            if not (0 < t.value < 110):
                continue
            if "Tctl" in t.name or "Core" in t.name:
                continue
            rows.append("%-18s %5.1f" % (t.name[:18], t.value))
        if b.cpu_temp is not None:
            rows.insert(1, "%-18s %5.1f" % ("CPU", b.cpu_temp))
        self.list.setText("\n".join(rows[:10]))


class FanRight(QWidget):
    """右侧风扇参数面板。"""

    def __init__(self, panel: "FanPanel", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.panel = panel
        self.bridge = FAN.instance()
        self.setFixedWidth(306)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        t = QLabel("风扇控制")
        t.setStyleSheet("font-size:15px;font-weight:700;color:%s;" % T.TEXT)
        lay.addWidget(t)

        self.state = QLabel("")
        self.state.setWordWrap(True)
        self.state.setStyleSheet("font-size:11px;color:%s;" % T.SUB)
        lay.addWidget(self.state)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:%s;" % T.BORDER)
        lay.addWidget(line)

        h = QLabel("一键操作")
        h.setStyleSheet("font-size:10px;font-weight:700;color:%s;letter-spacing:1.2px;" % T.DIM)
        lay.addWidget(h)

        for label, pct in (("全部 100%", 100.0), ("全部 70%", 70.0), ("全部 40%", 40.0)):
            b = QPushButton(label)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, v=pct: self._apply_all(v))
            lay.addWidget(b)

        rb = QPushButton("全部恢复自动")
        rb.setObjectName("Ghost")
        rb.setCursor(Qt.CursorShape.PointingHandCursor)
        rb.clicked.connect(self._restore_all)
        lay.addWidget(rb)

        lay.addSpacing(8)
        note = QLabel(
            "手动值会保持到下次重启，或直到 FanControl / BIOS 重新接管。\n\n"
            "程序退出时不会主动改回 BIOS 控制，"
            "想交还给主板请点「全部恢复自动」。")
        note.setWordWrap(True)
        note.setStyleSheet("font-size:11px;color:%s;line-height:150%%;" % T.DIM)
        lay.addWidget(note)
        lay.addStretch(1)

        self.refresh_state()

    def _guard(self) -> bool:
        if self.panel._fancontrol_pid is not None:
            self.state.setText("FanControl 正在接管，请先在中间点「接管风扇控制」。")
            self.state.setStyleSheet("font-size:11px;color:%s;" % T.WARN)
            return False
        return True

    def _apply_all(self, pct: float) -> None:
        if not self._guard():
            return
        for f in self.bridge.fans:
            self.bridge.set_pwm(f.id, pct)
        self.panel._refresh_ui()

    def _restore_all(self) -> None:
        if not self._guard():
            return
        self.bridge.restore_all()
        self.panel._refresh_ui()

    def refresh_state(self) -> None:
        b = self.bridge
        if not b.available:
            self.state.setText("硬件监控未初始化")
            return
        active = len([f for f in b.fans if f.rpm > 1])
        self.state.setText("通道 %d 个 · 运行中 %d 个 · 芯片 Nuvoton NCT6799D"
                           % (len(b.fans), active))
