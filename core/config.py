"""配置持久化（%APPDATA%/AuroraARGB/config.json）。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

APP_DIR_NAME = "AuroraARGB"

DEFAULTS: Dict[str, Any] = {
    "effect": "aurora",
    "brightness": 0.72,
    "speed": 1.0,
    "size": 0.4,
    "dir": 1,
    "c1": [0, 190, 255],
    "c2": [24, 8, 48],
    "pal": "极光",
    "led_count": 220,
    "fps": 30,
    "theme": "dark",
    "openrgb": True,
    "startup_apply": True,
    "tray_hint": False,
    "window": [1200, 780],
    "channels_off": [],
}


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    p = Path(base) / APP_DIR_NAME
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        p = Path(".")
    return p


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    path = config_path()
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if k in DEFAULTS or k in ("last_effect",):
                        cfg[k] = v
        except Exception:
            # 文件损坏（最常见的成因是进程在写盘瞬间被强杀，留下 0 字节）。
            # 把坏文件留一份副本方便排查，然后回落到默认值。
            try:
                if path.stat().st_size > 0:
                    path.replace(path.with_name("config.bad.json"))
            except Exception:
                pass
    return cfg


def save(cfg: Dict[str, Any]) -> None:
    """原子写入：先写临时文件再 replace。

    直接 open(path, "w") 在进程被强杀时会留下 0 字节文件，
    config.json 就是这样被截断过。
    """
    path = config_path()
    tmp = path.with_name("config.json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            if tmp.is_file():
                tmp.unlink()
        except Exception:
            pass
