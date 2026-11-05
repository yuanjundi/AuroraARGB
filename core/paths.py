"""资源路径解析（兼容 PyInstaller 单文件解包目录）。"""
from __future__ import annotations

import os
import sys


def app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def res(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    return os.path.join(app_root(), rel)
