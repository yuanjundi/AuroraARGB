# 第三方运行时（需自行获取）

本目录用于存放 **LibreHardwareMonitor** 的 .NET 程序集，风扇与温度读取依赖它。
这些 DLL 体积较大且遵循 MPL-2.0，未纳入版本库。

## 怎么获取

任选其一：

**A. 从 FanControl 目录复制（最省事）**

装了 [FanControl](https://github.com/Rem0o/FanControl.Releases) 的话，它自带全套依赖，
把 `D:\FanControl\` 下这几个文件拷到本目录：

```
LibreHardwareMonitorLib.dll
HidSharp.dll
DiskInfoToolkit.dll
RAMSPDToolkit-NDD.dll
System.Management.dll
System.IO.Ports.dll
Mono.Posix.NETStandard.dll
MonoPosixHelper.dll
libMonoPosixHelper.dll
```

**B. 从 NuGet 取**

```bash
curl -L -o lhm.nupkg https://www.nuget.org/api/v2/package/LibreHardwareMonitorLib
unzip lhm.nupkg -d lhm
cp lhm/runtimes/win-x64/lib/net10.0/LibreHardwareMonitorLib.dll .
```

其余依赖项按 `lhm/LibreHardwareMonitorLib.nuspec` 里的清单逐个取。

## 缺了会怎样

程序照常启动，灯效功能完全可用；只有风扇页会显示「无法初始化硬件监控」，
并给出具体是哪个文件缺失（也可以在「设置 → 硬件诊断」里看）。
