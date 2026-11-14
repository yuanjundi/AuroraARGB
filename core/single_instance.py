"""单实例守卫。

两个 AuroraARGB 进程同时运行，会同时向同一个 HID 端点写帧，硬件收到的是
两份交替的数据，表现就是灯乱闪。这里用「锁文件 + 本地套接字」保证全局只有
一个实例：第二次启动会唤醒已有实例的窗口，然后自己退出。

锁文件放在配置目录，QLockFile 会记录持有者 pid；进程被强杀后残留的锁
能在下次启动时自动清理，不会把用户永久挡在门外。
"""
from __future__ import annotations

import os
from typing import Callable, Optional

from PySide6.QtCore import QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "AuroraARGB-single-instance"

_lock: Optional[QLockFile] = None
_server: Optional[QLocalServer] = None


def acquire(lock_path: str, wait_ms: int = 250) -> bool:
    """抢到锁返回 True，说明本进程是唯一实例。

    wait_ms 是等锁的时间：正常启动等一小会儿就够（真有两个实例也不该干等），
    「重启并停厂商服务」那类场景要等旧进程真正退出，传大一点。
    """
    global _lock
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    except Exception:
        pass

    _lock = QLockFile(lock_path)
    # 0 = 不按时间判陈旧，交给 QLockFile 检查持有者进程是否还活着
    _lock.setStaleLockTime(0)
    if _lock.tryLock(wait_ms):
        return True

    # 锁还在，但持有者可能已经崩溃 —— 清掉再抢一次
    try:
        if _lock.removeStaleLockFile() and _lock.tryLock(wait_ms):
            return True
    except Exception:
        pass
    return False


def activate_existing(timeout: int = 900) -> bool:
    """通知已有实例把窗口叫到前台。连不上说明那把锁是陈旧的。"""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(timeout):
        return False
    try:
        sock.write(b"activate\n")
        sock.flush()
        sock.waitForBytesWritten(timeout)
        sock.disconnectFromServer()
    except Exception:
        pass
    return True


def serve(on_activate: Callable[[], None]) -> bool:
    """在唯一实例里起监听，收到「又有人启动了一次」就唤起窗口。"""
    global _server
    try:
        QLocalServer.removeServer(SERVER_NAME)
        _server = QLocalServer()
        _server.newConnection.connect(lambda: _drain(on_activate))
        return _server.listen(SERVER_NAME)
    except Exception:
        return False


def _drain(on_activate: Callable[[], None]) -> None:
    if _server is None:
        return
    while _server.hasPendingConnections():
        sock = _server.nextPendingConnection()
        if sock is None:
            break
        sock.readyRead.connect(sock.readAll)
        sock.disconnected.connect(sock.deleteLater)
    try:
        on_activate()
    except Exception:
        pass
