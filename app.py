"""Aurora ARGB Studio 入口。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


# 「登录界面就启动」用的守护模式：必须在导入 PySide6 之前分流。
# 那时没有用户会话，Qt 的窗口系统起不来，所以走纯 Python 引擎。
if "--boot" in sys.argv:
    from boot_agent import main as _boot_main
    sys.exit(_boot_main())


# 告诉守护进程「界面的主程序已经起来了，你可以让位了」。
# 先写 pid，再等它退出，最后才创建窗口，避免两边同时写 HID 把灯写花。
def _claim_gui_slot() -> str:
    try:
        from core import config as CFG
        p = os.path.join(str(CFG.config_dir()), "gui.pid")
        with open(p, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return p
    except Exception:
        return ""


_PID_FILE = _claim_gui_slot()
if _PID_FILE:
    import time as _time
    _time.sleep(0.9)


def _release_gui_slot() -> None:
    try:
        if _PID_FILE and os.path.isfile(_PID_FILE):
            os.remove(_PID_FILE)
    except Exception:
        pass


import atexit

atexit.register(_release_gui_slot)


from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QApplication

from core.paths import res
from ui import theme as T
from ui.main_window import MainWindow


def main() -> None:
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Aurora ARGB Studio")
    app.setApplicationDisplayName("Aurora ARGB Studio")
    app.setOrganizationName("Aurora")
    # 关窗口只是收进托盘，不能让 Qt 因为「最后一个窗口关闭」就把进程杀掉
    app.setQuitOnLastWindowClosed(False)

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(T.BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(T.TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(T.PANEL))
    pal.setColor(QPalette.ColorRole.Text, QColor(T.TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(T.PANEL3))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(T.TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(T.ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#04121A"))
    app.setPalette(pal)

    app.setStyleSheet(T.QSS)
    app.setFont(QFont(T.FONT, 9))

    ico = res("app.ico")
    if os.path.isfile(ico):
        app.setWindowIcon(QIcon(ico))

    # 以管理员身份重启后自动接管：停掉厂商常驻服务，避免两边抢设备导致灯闪
    if "--stop-vendor" in sys.argv:
        try:
            from core.backends.colorful import ColorfulBackend
            ColorfulBackend.stop_vendor_service()
        except Exception:
            pass

    win = MainWindow(start_tab=1 if "--fan" in sys.argv else 0)
    win.show()

    # 自测用：--shot <路径> 启动若干秒后自动截图并退出
    if "--shot" in sys.argv:
        idx = sys.argv.index("--shot")
        if idx + 1 < len(sys.argv):
            target = sys.argv[idx + 1]

            def _snap() -> None:
                try:
                    win.grab().save(target)
                except Exception:
                    pass
                app.quit()

            from PySide6.QtCore import QTimer as _QT
            _QT.singleShot(7000, _snap)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
