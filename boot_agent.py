"""开机灯效守护（无界面）。

用于「登录界面就启动」这个场景：由计划任务以 SYSTEM 身份在开机时拉起，
此时 Windows 还停在登录界面，没有任何用户会话，PySide6 的窗口系统不可用，
所以这里**完全不 import Qt**，只用 core 里的纯 Python 部分驱动灯效。

交接规则：
  · 用户登录后启动带界面的主程序，主程序会写一个 gui.pid
  · 本进程每隔 0.5 秒检查该 pid 是否存活，存活就主动退出，让出路权
  · 主程序崩溃留下的僵尸 pid 会被 pid_exists 判为 False，不影响守护继续跑
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _cfg_dir() -> str:
    """SYSTEM 身份下 APPDATA 指向 systemprofile，要回到真实用户的配置目录，
    否则守护进程会读到默认配置（灯效和自己设的不一样）。"""
    try:
        from core import config as CFG
    except Exception:
        return os.path.dirname(os.path.abspath(__file__))
    base = os.environ.get("APPDATA", "")
    if "systemprofile" in base.lower():
        best = None
        root = r"C:\Users"
        try:
            for name in os.listdir(root):
                p = os.path.join(root, name, "AppData", "Roaming", "AuroraARGB")
                cfg = os.path.join(p, "config.json")
                if os.path.isfile(cfg):
                    t = os.path.getmtime(cfg)
                    if best is None or t > best[0]:
                        best = (t, p)
        except Exception:
            pass
        if best:
            return best[1]
    return str(CFG.config_dir())


def _load_cfg() -> dict:
    import json
    from core import config as CFG
    cfg = dict(CFG.DEFAULTS)
    p = os.path.join(_cfg_dir(), "config.json")
    if os.path.isfile(p):
        try:
            raw = json.load(open(p, "r", encoding="utf-8"))
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if k in CFG.DEFAULTS:
                        cfg[k] = v
        except Exception:
            pass
    return cfg


def _log(msg: str) -> None:
    try:
        path = os.path.join(_cfg_dir(), "boot.log")
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (stamp, msg))
    except Exception:
        pass


def _gui_alive() -> bool:
    """带界面的主程序是否在运行（它会在配置目录写 gui.pid）。"""
    try:
        p = os.path.join(_cfg_dir(), "gui.pid")
        if not os.path.isfile(p):
            return False
        try:
            pid = int(open(p, "r", encoding="utf-8").read().strip())
        except Exception:
            return False
        if pid <= 0:
            return False
        try:
            import psutil
            return psutil.pid_exists(pid)
        except Exception:
            return False
    except Exception:
        return False


def main() -> int:
    _log("boot agent 启动, argv=%s" % " ".join(sys.argv))
    try:
        from core import config as CFG
        from core.backends.colorful import ColorfulBackend
        from core.engine import Engine
    except Exception:
        _log("导入失败:\n" + traceback.format_exc())
        return 1

    if _gui_alive():
        _log("主程序已在运行，本次不接管")
        return 0

    cfg = _load_cfg()
    eng = Engine()
    eng.set_effect(cfg.get("effect", "aurora"))
    eng.params["speed"] = float(cfg.get("speed", 1.0))
    eng.params["size"] = float(cfg.get("size", 0.4))
    eng.params["dir"] = int(cfg.get("dir", 1))
    eng.params["c1"] = tuple(cfg.get("c1", [0, 190, 255]))
    eng.params["c2"] = tuple(cfg.get("c2", [24, 8, 48]))
    eng.set_param("pal", cfg.get("pal", "极光"))
    eng.set_brightness(float(cfg.get("brightness", 0.72)))

    backend = ColorfulBackend(int(cfg.get("led_count", 220)))
    ok = False
    try:
        chans = backend.scan()
        for ch in chans:
            eng.register(ch, backend)
        ok = bool(chans)
    except Exception:
        _log("扫描设备失败:\n" + traceback.format_exc())

    _log("设备: %s (ready=%s)" % ("已连接" if ok else "未找到", backend.ready))

    fps = max(10, min(60, int(cfg.get("fps", 30))))
    frame_time = 1.0 / fps
    last = time.perf_counter()
    frames = 0
    started = time.time()
    last_log = started

    while True:
        try:
            if _gui_alive():
                _log("检测到主程序，守护退出（已推 %d 帧）" % frames)
                break

            now = time.perf_counter()
            dt = now - last
            last = now
            if dt > 0.5:
                dt = frame_time

            if not backend.ready:
                # 设备可能被别的程序抢占/热插拔，定期重试
                if int(time.time()) % 10 == 0:
                    try:
                        if backend.open() and not eng.states:
                            for ch in backend.scan():
                                eng.register(ch, backend)
                    except Exception:
                        pass

            eng.tick(dt)
            frames += 1

            # 每 5 分钟记一次心跳，避免日志无限膨胀
            if time.time() - last_log > 300:
                last_log = time.time()
                _log("心跳: 已运行 %d 分钟, %d 帧, 错误 %d"
                     % (int((time.time() - started) / 60), frames, eng.writer.errors))

            time.sleep(frame_time)
        except KeyboardInterrupt:
            break
        except Exception:
            _log("主循环异常:\n" + traceback.format_exc())
            time.sleep(1.0)

    try:
        eng.shutdown()
        backend.close()
    except Exception:
        pass
    _log("boot agent 退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
