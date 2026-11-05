"""开机自启管理。

三种模式（互斥，切换时先清掉其它）：
  · 注册表 Run 项     —— 登录后启动。**不需要管理员**，最稳，默认推荐
  · 计划任务 Logon    —— 登录后启动，带最高权限。需要管理员创建
  · 计划任务 Boot     —— 系统启动就以 SYSTEM 拉起无界面守护，登录前灯就在跑。
                        需要管理员创建，且 SYSTEM 会话下 HID 是否可访问要看实机

经验教训：计划任务那条路在「当前会话不是管理员」时会静默失败
（schtasks 返回"拒绝访问"），用户以为设了其实没设。所以默认走注册表。
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Dict, Tuple

BOOT_TASK = "AuroraARGB Boot"
LOGON_TASK = "AuroraARGB Logon"

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "AuroraARGB"


def exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def _tr(extra: str = "") -> str:
    """拼出任务里要执行的完整命令行（含引号）。"""
    if getattr(sys, "frozen", False):
        core = '"%s"' % sys.executable
    else:
        core = '"%s" "%s"' % (sys.executable, os.path.abspath(sys.argv[0]))
    return (core + " " + extra).strip()


def _run(args) -> Tuple[bool, str]:
    try:
        r = subprocess.run(
            args, capture_output=True, timeout=20,
            creationflags=0x08000000,
        )
        raw = (r.stdout or b"") + (r.stderr or b"")
        try:
            # Windows 命令行工具输出的是本地代码页（中文系统为 GBK），
            # 用 utf-8 解码会直接抛 UnicodeDecodeError
            out = raw.decode("mbcs", errors="replace").strip()
        except Exception:
            out = raw.decode("utf-8", errors="replace").strip()
        return r.returncode == 0, out
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------- 注册表 Run

def run_exists() -> bool:
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, RUN_NAME)
            return True
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def run_command() -> str:
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(key, RUN_NAME)
            return str(val)
        finally:
            winreg.CloseKey(key)
    except Exception:
        return ""


def enable_run() -> Tuple[bool, str]:
    """登录后自启。不需要管理员，最可靠。"""
    import winreg
    disable_all()
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_ALL_ACCESS)
        try:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, '"%s"' % exe_path())
        finally:
            winreg.CloseKey(key)
        return True, "已写入登录自启（注册表 Run）"
    except Exception as exc:
        return False, str(exc)


def disable_run() -> None:
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_ALL_ACCESS)
        try:
            winreg.DeleteValue(key, RUN_NAME)
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass


# ---------------------------------------------------------------- 计划任务

def task_exists(name: str) -> bool:
    ok, _ = _run(["schtasks", "/query", "/tn", name])
    return ok


def status() -> Dict[str, bool]:
    return {
        "boot": task_exists(BOOT_TASK),
        "logon": task_exists(LOGON_TASK),
        "run": run_exists(),
    }


def disable_all() -> Tuple[bool, str]:
    msgs = []
    disable_run()
    for n in (BOOT_TASK, LOGON_TASK):
        if task_exists(n):
            ok, out = _run(["schtasks", "/delete", "/tn", n, "/f"])
            msgs.append("%s %s" % (n, "已删除" if ok else ("失败: " + out)))
    return True, "；".join(msgs) if msgs else "已清理自启项"


def enable_logon() -> Tuple[bool, str]:
    """登录后启动（计划任务，最高权限）。需要管理员。"""
    disable_all()
    ok, out = _run([
        "schtasks", "/create", "/tn", LOGON_TASK,
        "/tr", _tr(),
        "/sc", "onlogon", "/rl", "HIGHEST", "/f",
    ])
    if ok:
        return True, "已创建登录计划任务"
    return False, out or "创建失败（需要管理员权限）"


def enable_boot() -> Tuple[bool, str]:
    """开机即启动（SYSTEM，无界面守护，登录界面时灯就已经在跑）。需要管理员。"""
    disable_all()
    ok, out = _run([
        "schtasks", "/create", "/tn", BOOT_TASK,
        "/tr", _tr("--boot"),
        "/sc", "onstart", "/ru", "SYSTEM", "/rl", "HIGHEST", "/f",
    ])
    if ok:
        return True, "已创建开机计划任务（登录前启动）"
    return False, out or "创建失败（需要管理员权限）"


def run_now(name: str) -> Tuple[bool, str]:
    return _run(["schtasks", "/run", "/tn", name])


def stop_now(name: str) -> Tuple[bool, str]:
    return _run(["schtasks", "/end", "/tn", name])
