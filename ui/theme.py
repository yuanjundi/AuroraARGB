"""界面主题：配色与全局样式表。"""
from __future__ import annotations

BG = "#080A0E"
BG2 = "#0C0F15"
PANEL = "#111520"
PANEL2 = "#161B27"
PANEL3 = "#1D2331"
BORDER = "#232A38"
BORDER_L = "#2E3748"
TEXT = "#E9EEF8"
SUB = "#76839A"
DIM = "#4A5466"
ACCENT = "#3DDCFF"
ACCENT2 = "#8B5CF6"
OK = "#38E0A0"
WARN = "#FFB020"
ERR = "#FF5C72"

FONT = "Microsoft YaHei UI"

QSS = f"""
* {{
    font-family: "{FONT}", "Segoe UI", sans-serif;
    outline: none;
}}
QWidget {{
    color: {TEXT};
    font-size: 13px;
}}
QMainWindow, #Root {{
    background: {BG};
}}
#Sidebar {{
    background: {BG2};
    border-right: 1px solid {BORDER};
}}
#RightPanel {{
    background: {BG2};
    border-left: 1px solid {BORDER};
}}
#Card {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
#CardFlat {{
    background: {PANEL2};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLabel[role="h1"] {{
    font-size: 22px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel[role="h2"] {{
    font-size: 15px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel[role="sec"] {{
    font-size: 11px;
    font-weight: 700;
    color: {DIM};
    letter-spacing: 1px;
}}
QLabel[role="sub"] {{
    color: {SUB};
    font-size: 12px;
}}
QLabel[role="mono"] {{
    color: {SUB};
    font-size: 11px;
    font-family: "Consolas", monospace;
}}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 2px 2px 2px 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_L}; border-radius: 4px; min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: #3E4A60; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; }}
QScrollBar::handle:horizontal {{ background: {BORDER_L}; border-radius: 4px; min-width: 32px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QSlider::groove:horizontal {{
    height: 6px; background: {PANEL3}; border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT}, stop:1 {ACCENT2});
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 15px; height: 15px; margin: -5px 0; border-radius: 8px;
    background: #FFFFFF; border: 2px solid {ACCENT};
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT}; border: 2px solid #FFFFFF;
}}

QComboBox {{
    background: {PANEL3}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 6px 10px; color: {TEXT};
}}
QComboBox:hover {{ border-color: {BORDER_L}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {SUB};
}}
QComboBox QAbstractItemView {{
    background: {PANEL2}; border: 1px solid {BORDER_L}; border-radius: 8px;
    selection-background-color: {PANEL3}; color: {TEXT}; padding: 4px;
}}

QToolTip {{
    background: {PANEL3}; color: {TEXT}; border: 1px solid {BORDER_L};
    border-radius: 6px; padding: 6px 8px;
}}
QPushButton {{
    background: {PANEL3}; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 7px 14px; color: {TEXT};
}}
QPushButton:hover {{ background: #242C3C; border-color: {BORDER_L}; }}
QPushButton:pressed {{ background: #1A2030; }}
QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT}, stop:1 {ACCENT2});
    border: none; color: #06121A; font-weight: 700;
}}
QPushButton#Primary:hover {{ opacity: 0.9; }}
QPushButton#Ghost {{
    background: transparent; border: 1px solid {BORDER};
    color: {SUB}; padding: 6px 10px;
}}
QPushButton#Ghost:hover {{ color: {TEXT}; border-color: {BORDER_L}; }}

QSpinBox {{
    background: {PANEL3}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 5px 8px; color: {TEXT}; min-width: 74px;
    selection-background-color: {ACCENT};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 16px; border: none; background: transparent;
}}
QSpinBox::up-arrow {{
    image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-bottom: 5px solid {SUB}; width: 0; height: 0;
}}
QSpinBox::down-arrow {{
    image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {SUB}; width: 0; height: 0;
}}
QCheckBox {{ color: {TEXT}; spacing: 9px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px;
    border: 1px solid {BORDER_L}; background: {PANEL3};
}}
QCheckBox::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {ACCENT}, stop:1 {ACCENT2});
    border: 1px solid {ACCENT};
}}
QDialog {{ background: {BG2}; }}
"""

LIGHT_QSS = """
#Sidebar, #RightPanel { background: #F4F6FA; border-color: #E2E7F0; }
#Root { background: #FFFFFF; }
#Card { background: #FFFFFF; border: 1px solid #E4E9F2; }
#CardFlat { background: #F6F8FC; border: 1px solid #E4E9F2; }
QLabel { color: #16202F; }
QSlider::groove:horizontal { background: #E2E7F0; }
QComboBox { background: #FFFFFF; border: 1px solid #E2E7F0; color: #16202F; }
QPushButton { background: #FFFFFF; border: 1px solid #E2E7F0; color: #16202F; }
"""
