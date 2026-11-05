"""生成应用图标：深色圆角底 + 霓虹渐变光环。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QConicalGradient, QImage, QLinearGradient, QPainter,
    QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QApplication

app = QApplication([])

S = 512
img = QImage(S, S, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

# 底：圆角方形 + 微弱径向亮部
bg = QPainterPath()
bg.addRoundedRect(QRectF(10, 10, S - 20, S - 20), 104, 104)
g = QLinearGradient(0, 0, S, S)
g.setColorAt(0.0, QColor("#1A2436"))
g.setColorAt(0.5, QColor("#0C121C"))
g.setColorAt(1.0, QColor("#05070B"))
p.fillPath(bg, QBrush(g))

cx = cy = S / 2.0
R = 156.0
W = 48.0

# 极淡的中心氛围光（单次径向渐变，不会出现同心圈）
amb = QRadialGradient(cx, cy, R * 1.5)
amb.setColorAt(0.00, QColor(70, 170, 255, 26))
amb.setColorAt(0.55, QColor(70, 140, 255, 10))
amb.setColorAt(1.00, QColor(0, 0, 0, 0))
p.setPen(Qt.PenStyle.NoPen)
p.setBrush(QBrush(amb))
p.drawEllipse(QPointF(cx, cy), R * 1.5, R * 1.5)

# 光环：锥形渐变
con = QConicalGradient(cx, cy, -90.0)
for pos, c in [
    (0.00, "#54E8FF"), (0.14, "#3DDCFF"), (0.34, "#7C7BFF"),
    (0.50, "#C860E8"), (0.66, "#7C7BFF"), (0.86, "#3DDCFF"), (1.00, "#54E8FF"),
]:
    con.setColorAt(pos, QColor(c))
ring = QPainterPath()
ring.addEllipse(QPointF(cx, cy), R, R)
ring.addEllipse(QPointF(cx, cy), R - W, R - W)
ring.setFillRule(Qt.FillRule.OddEvenFill)
p.fillPath(ring, QBrush(con))

# 环的描边让边缘更利落
p.setBrush(Qt.BrushStyle.NoBrush)
p.setPen(QPen(QColor(255, 255, 255, 46), 1.6))
p.drawEllipse(QPointF(cx, cy), R - 0.8, R - 0.8)
p.setPen(QPen(QColor(255, 255, 255, 30), 1.6))
p.drawEllipse(QPointF(cx, cy), R - W + 0.8, R - W + 0.8)

# 中心发光球
glow = QRadialGradient(cx, cy, 62)
glow.setColorAt(0.0, QColor(120, 225, 255, 120))
glow.setColorAt(1.0, QColor(120, 225, 255, 0))
p.setPen(Qt.PenStyle.NoPen)
p.setBrush(QBrush(glow))
p.drawEllipse(QPointF(cx, cy), 62, 62)

core = QRadialGradient(cx - 7, cy - 9, 30)
core.setColorAt(0.0, QColor("#FFFFFF"))
core.setColorAt(0.55, QColor("#CFF6FF"))
core.setColorAt(1.0, QColor("#49C4FF"))
p.setBrush(QBrush(core))
p.drawEllipse(QPointF(cx, cy), 27, 27)

p.end()

png = os.path.join(HERE, "app_icon.png")
img.save(png)
print("saved", png)

try:
    from PIL import Image
    im = Image.open(png).convert("RGBA")
    ico = os.path.join(HERE, "app.ico")
    im.save(ico, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("saved", ico)
except Exception as exc:
    print("ico failed:", exc)
