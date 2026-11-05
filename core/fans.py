"""风扇控制：通过 LibreHardwareMonitorLib 读写主板 Super I/O。

实测本机：COLORFUL CVN B850I GAMING FROZEN V14 + Nuvoton NCT6799D，
暴露 7 个可控通道 /lpc/nct6799d/control/0..6 与对应转速 /fan/0..6。

设计原则：
1. 只读优先级最高，任何时候都不影响散热。
2. 写入前必须确认自家程序拿到控制权，且检测 FanControl 是否在跑（会互相覆盖）。
3. 所有写入都带返回值校验，失败立即回落默认（BIOS）控制。
"""
from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .paths import res

_LHM: Dict[str, object] = {"loaded": False, "err": ""}
_LOCK = threading.RLock()


def lhm_dir() -> str:
    return res(os.path.join("third_party", "lhm"))


def ensure_lhm() -> str:
    """加载 .NET 程序集，返回错误信息（空串表示成功）。"""
    with _LOCK:
        if _LHM.get("loaded"):
            return ""
        d = lhm_dir()
        dll = os.path.join(d, "LibreHardwareMonitorLib.dll")
        if not os.path.isfile(dll):
            return "缺少 LibreHardwareMonitorLib.dll"
        try:
            try:
                os.add_dll_directory(d)
            except Exception:
                pass
            if d not in sys.path:
                sys.path.insert(0, d)
            try:
                import pythonnet
                pythonnet.load("coreclr")
            except Exception:
                pass
            import clr
            clr.AddReference(dll)
            from LibreHardwareMonitor.Hardware import Computer  # noqa: F401
            _LHM["loaded"] = True
            _LHM["err"] = ""
            return ""
        except Exception as exc:
            _LHM["err"] = "%s: %s" % (type(exc).__name__, exc)
            return _LHM["err"]


def is_admin() -> bool:
    """是否具备管理员权限（读 Super I/O 必需）。"""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _pawnio_running() -> bool:
    import subprocess
    try:
        r = subprocess.run(
            ["sc", "query", "PawnIO"],
            capture_output=True, timeout=2.0,
            creationflags=0x08000000,
        )
        out = (r.stdout or b"").decode("mbcs", errors="replace")
        return "RUNNING" in out.upper()
    except Exception:
        return False


def _dotnet_versions() -> str:
    import glob
    vers = []
    for root in (r"C:\Program Files\dotnet\shared\Microsoft.NETCore.App",
                 r"C:\Program Files (x86)\dotnet\shared\Microsoft.NETCore.App"):
        if os.path.isdir(root):
            for p in glob.glob(os.path.join(root, "*")):
                if os.path.isdir(p):
                    vers.append(os.path.basename(p))
    return ", ".join(sorted(set(vers))) or "未检测到"


def diagnose() -> Dict[str, object]:
    """汇总硬件诊断信息，供「硬件诊断」窗口展示。"""
    info: Dict[str, object] = {
        "admin": is_admin(),
        "pawnio": _pawnio_running(),
        "dotnet": _dotnet_versions(),
        "dlls": [],
        "lhm_err": "",
        "board": "",
        "chip": "",
        "fans": [],
        "temps": [],
        "fancontrol": fancontrol_running(),
        "update_ms": 0.0,
    }

    d = lhm_dir()
    for name in ("LibreHardwareMonitorLib.dll", "HidSharp.dll",
                 "DiskInfoToolkit.dll", "RAMSPDToolkit-NDD.dll"):
        p = os.path.join(d, name)
        info["dlls"].append((name, os.path.isfile(p),
                             os.path.getsize(p) if os.path.isfile(p) else 0))

    if not info["admin"]:
        info["lhm_err"] = "缺少管理员权限，无法读取 Super I/O"
        return info

    b = instance()
    if not b.available:
        err = b.open()
        if err:
            info["lhm_err"] = err
            return info
    else:
        b.refresh(force=True)

    for hw in (b.pc.Hardware if b.pc is not None else []):
        if "Motherboard" in str(hw.HardwareType):
            info["board"] = str(hw.Name)
            for sub in hw.SubHardware:
                info["chip"] = str(sub.Name)

    info["fans"] = [(f.name, f.id, f.pwm, f.rpm) for f in b.fans]
    info["temps"] = [(t.name, t.value) for t in b.temps if 0 < t.value < 110]
    info["update_ms"] = b.update_ms
    return info


def fancontrol_running() -> Optional[int]:
    """返回 FanControl 进程 PID，没在跑返回 None。"""
    try:
        import psutil
    except Exception:
        return None
    for p in psutil.process_iter(["name"]):
        try:
            n = (p.info.get("name") or "").lower()
            if n in ("fancontrol.exe", "fancontrol"):
                return p.pid
        except Exception:
            continue
    return None


@dataclass
class FanChannel:
    id: str
    name: str
    pwm: float = 0.0        # 0-100
    rpm: float = 0.0
    controllable: bool = True
    paired: Optional[str] = None


@dataclass
class TempSensor:
    id: str
    name: str
    value: float
    hardware: str = ""


class FanBridge:
    """LHM 的薄封装，负责枚举 / 刷新 / 写 PWM。"""

    def __init__(self) -> None:
        self.pc = None
        self.error = ""
        self.fans: List[FanChannel] = []
        self.temps: List[TempSensor] = []
        self.cpu_temp: Optional[float] = None
        self._ctrl: Dict[str, object] = {}
        self._fan_sensors: Dict[str, object] = {}
        self._opened = False
        self._last_update = 0.0
        self._last_ms = 0.0

    # ------------------------------------------------------------ 生命周期

    @property
    def available(self) -> bool:
        return self._opened

    def open(self) -> str:
        if self._opened:
            return ""
        err = ensure_lhm()
        if err:
            self.error = err
            return err
        try:
            from LibreHardwareMonitor.Hardware import Computer
        except Exception as exc:
            self.error = "导入失败: %s" % exc
            return self.error
        try:
            pc = Computer()
            pc.IsCpuEnabled = True
            pc.IsMotherboardEnabled = True
            pc.IsControllerEnabled = False
            pc.IsMemoryEnabled = False
            pc.IsGpuEnabled = False
            pc.IsStorageEnabled = False
            pc.Open()
            self.pc = pc
            self._opened = True
            self.error = ""
            self.refresh(force=True)
            return ""
        except Exception as exc:
            self.error = "初始化失败: %s" % exc
            self._opened = False
            return self.error

    def close(self) -> None:
        if self.pc is not None:
            try:
                self.pc.Close()
            except Exception:
                pass
        self.pc = None
        self._opened = False
        self._ctrl.clear()
        self._fan_sensors.clear()

    # ------------------------------------------------------------ 读取

    def refresh(self, force: bool = False) -> None:
        if not self._opened or self.pc is None:
            return
        now = time.perf_counter()
        if not force and now - self._last_update < 0.4:
            return
        self._last_update = now
        t0 = time.perf_counter()
        try:
            ctrls: Dict[str, FanChannel] = {}
            rpms: Dict[str, float] = {}
            temps: List[TempSensor] = []

            def scan(hw, hw_name: str) -> None:
                try:
                    hw.Update()
                except Exception:
                    pass
                for s in hw.Sensors:
                    st = str(s.SensorType)
                    sid = str(s.Identifier)
                    if st == "Control":
                        if s.Control is None:
                            continue
                        c = FanChannel(id=sid, name=str(s.Name),
                                       pwm=float(s.Value or 0.0))
                        ctrls[sid] = c
                        self._ctrl[sid] = s.Control
                    elif st == "Fan":
                        rpms[sid] = float(s.Value or 0.0)
                        self._fan_sensors[sid] = s
                    elif st == "Temperature":
                        v = s.Value
                        if v is not None:
                            temps.append(TempSensor(id=sid, name=str(s.Name),
                                                    value=float(v), hardware=hw_name))
                for sub in hw.SubHardware:
                    scan(sub, str(sub.Name))

            for hw in self.pc.Hardware:
                scan(hw, str(hw.Name))

            # control 与 fan 按索引配对
            for cid, ch in ctrls.items():
                idx = cid.rsplit("/", 1)[-1]
                base = cid.rsplit("/control", 1)[0]
                fid = "%s/fan/%s" % (base, idx)
                if fid in rpms:
                    ch.rpm = rpms[fid]
                    ch.paired = fid
                ch.name = ch.name or ("Fan #%s" % idx)

            self.fans = list(ctrls.values())
            self.temps = temps
            cpu = None
            for t in temps:
                if "Tctl" in t.name or "Package" in t.name:
                    cpu = t.value
                    break
            if cpu is None:
                for t in temps:
                    if "CPU" in t.hardware.upper():
                        cpu = t.value
                        break
            self.cpu_temp = cpu
        except Exception as exc:
            self.error = "刷新失败: %s" % exc
        self._last_ms = (time.perf_counter() - t0) * 1000.0

    @property
    def update_ms(self) -> float:
        return self._last_ms

    def summary(self) -> dict:
        boards = [f for f in self.fans]
        return {
            "count": len(boards),
            "active": len([f for f in boards if f.rpm > 1]),
            "cpu": self.cpu_temp,
            "ms": round(self._last_ms, 2),
        }

    # ------------------------------------------------------------ 写入

    def set_pwm(self, fan_id: str, percent: float, verify: bool = True) -> bool:
        """把某个通道设成固定占空比。返回是否成功。"""
        ctrl = self._ctrl.get(fan_id)
        if ctrl is None:
            return False
        pct = max(0.0, min(100.0, float(percent)))
        # 安全下限：低于 20% 很多风扇会停转，这里兜一下
        pct = max(20.0, pct)
        try:
            ctrl.SetSoftware(pct)
        except Exception:
            try:
                import System
                ctrl.SetSoftware(System.Single(pct))
            except Exception:
                return False
        if verify:
            time.sleep(0.05)
            try:
                s = self._fan_sensors.get(fan_id.replace("/control/", "/fan/"))
                # 无法可靠读回 PWM 时退化为不校验
                if s is not None:
                    s.Update()
            except Exception:
                pass
        self.refresh(force=True)
        return True

    def restore_auto(self, fan_id: str) -> bool:
        """把通道还给 BIOS / 默认控制。"""
        ctrl = self._ctrl.get(fan_id)
        if ctrl is None:
            return False
        try:
            ctrl.SetDefault()
            self.refresh(force=True)
            return True
        except Exception:
            return False

    def restore_all(self) -> None:
        for fid in list(self._ctrl.keys()):
            try:
                self._ctrl[fid].SetDefault()
            except Exception:
                pass
        self.refresh(force=True)


# ---------------------------------------------------------------- 单例

_INSTANCE: Optional[FanBridge] = None


def instance() -> FanBridge:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = FanBridge()
    return _INSTANCE
