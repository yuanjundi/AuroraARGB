# Aurora ARGB Studio

Windows 下的机箱灯效与风扇控制器。**直接驱动主板上的 ARGB 控制器**，不依赖 iGame Center 等厂商软件；风扇 PWM 通过 Super I/O 芯片读写，不占用 BIOS 设置。

主打低占用：默认 30 fps 下单核约 6%，内存约 100 MB，窗口最小化后完全停帧。

---

## 功能

**灯效**

- 25 种内置效果：静态、呼吸、彩虹、跑马灯、彗星、极光、等离子、火焰、流星雨、涟漪、雷暴、频谱、负载律动、温度律动……
- 亮度 / 速度 / 尺寸 / 方向 / 主副色实时调节
- 四组预设场景一键切换
- 输出总开关，熄灯但保留配置

**风扇**

- 读取每个通道的转速（RPM）与 PWM 占空比
- 手动调速，PWM 下限锁 20% 防止风扇停转
- 实时 CPU / 主板 / CCD 温度
- 一键全部 100% / 70% / 40% / 恢复自动

**其他**

- 关闭窗口收进托盘，灯效和风扇继续跑
- 开机自启（登录后 / 登录前两种模式）
- 全局单文件 exe，或 Inno Setup 安装包
- 内置硬件诊断页，排障一眼看到卡在哪

---

## 支持的硬件

**已验证**

| 项目 | 型号 |
|---|---|
| 主板 | COLORFUL CVN B850I GAMING FROZEN V14 |
| ARGB 控制器 | USB HID `2F4C:1013`，`usage_page=0xFF01` |
| Super I/O | Nuvoton NCT6799D（7 个风扇通道） |

**理论支持**

- 其它使用同一套 HID 协议的七彩虹主板（协议同源，灯珠数需自行调整）
- 其它 Super I/O 芯片的风扇控制，只要 LibreHardwareMonitor 支持（Nuvoton NCT67xx 系列、ITE IT86xx 系列、Fintek 等）
- 显卡 / 内存 / 其它品牌主板灯效：通过 OpenRGB SDK 接入

**不支持**

- 笔记本、一体机
- 需要厂商私有加密握手的设备

---

## 快速开始

### 用安装包

下载 `AuroraARGB-Setup-*.exe`，双击安装。默认装到 `C:\Program Files\AuroraARGB`，安装向导里可以改路径。

安装时可勾选「开机自动启动」，装完会在 `HKCU\...\Run` 写入自启项，卸载时自动清理。

### 用绿色版

下载 `AuroraARGB.exe` 直接运行。exe 自带 `requireAdministrator` 清单，双击即以管理员身份启动，无需右键。

### 首次使用注意

如果机箱灯在闪或忽明忽暗，说明厂商服务（`iGameCenterService`）还在后台抢同一个 HID 端点。打开软件 →「设置」→「停止厂商服务」即可独占控制，重启电脑后厂商服务会自动恢复。

---

## 从源码构建

**环境**

- Windows 10/11 x64
- Python 3.11+
- .NET 运行时（风扇功能依赖，`dotnet --list-runtimes` 可查）

**步骤**

```bash
pip install PySide6 hidapi psutil pythonnet pyinstaller
```

1. 取 LibreHardwareMonitor 运行时，放到 `third_party/lhm/`：

   从 [LibreHardwareMonitor Releases](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases)
   或任意已安装的 [FanControl](https://github.com/Rem0o/FanControl.Releases) 目录，
   复制以下文件过去：

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

2. 打包

   ```bash
   pyinstaller build.spec --noconfirm --clean
   ```

3. 打安装包（可选，需要 [Inno Setup 6](https://jrsoftware.org/isdl.php)）

   ```bash
   ISCC.exe install.iss
   ```

**调试参数**

| 参数 | 作用 |
|---|---|
| `--boot` | 无界面守护模式，登录前自启用 |
| `--fan` | 启动直接进风扇页 |
| `--shot <path>` | 启动 7 秒后自动截图并退出，用于自动化验证 |

---

## 工作原理

### 灯效：直接怼 HID

七彩虹的 ARGB 控制器是一个普通 USB HID 设备，协议结构：

```
包头  [0x00, 0x01, 0x00, 0x88, 包序号]
数据  20 颗灯珠 × 3 字节 RGB
提交  末包发全 0 并置 0xFF
```

无校验和、无需握手。按 20 颗一包切片推流即可，灯珠总数按型号配置（同系列默认 220）。

灯效计算是纯 Python 的逐帧函数，`Engine.tick()` 里按时间步进，结果通过独立线程推给设备，UI 线程只负责画预览。

### 风扇：借道 LibreHardwareMonitor

风扇挂在主板的 Super I/O 芯片上，Windows 不提供任何用户态接口，必须走内核驱动。本项目的做法是：

1. 用 `pythonnet` 加载 LibreHardwareMonitor 的 .NET 程序集（`core/fans.py`）
2. LHM 内部通过 PawnIO 驱动访问 Super I/O
3. 枚举出 `Control` / `Fan` / `Temperature` 传感器
4. 写值调用 `sensor.Control.SetSoftware(percent)`

不自己啃寄存器是刻意的选择：芯片型号识别、bank 切换、风扇映射表都是坑，写错一格可能让风扇停转。LHM 在这块经过社区长期验证，复用它比重新发明安全得多。

### 登录前自启：无界面守护

「开机即启动」模式由计划任务以 SYSTEM 拉起 `AuroraARGB.exe --boot`。此时 Windows 还停在登录界面，没有用户会话，Qt 的窗口系统起不来，所以 `boot_agent.py` **一行 Qt 都不 import**，只用 `core` 里的纯 Python 引擎跑循环。

交接靠一个 pid 文件：主程序启动时写 `%APPDATA%\AuroraARGB\gui.pid`，守护进程每 0.5 秒检查该 pid 是否存活，存活就主动退场。

---

## 已知限制

- **风扇功能需要管理员权限**，普通权限下 `pawnio_open` 返回 `ACCESS_DENIED`，UI 会降级为只读提示
- **与 FanControl 存在冲突**：两者底层是同一套 LHM，同时写 PWM 会互相覆盖。程序检测到 FanControl 在跑时会锁住滑块，需手动「接管」
- **显卡灯效未实机验证**（开发机是核显平台），OpenRGB 通路按标准 SDK 实现
- 灯珠数量按型号常量配置，异型号主板可能需要手动调
- 仅支持 Windows

---

## 目录结构

```
argb_studio/
├── app.py                 程序入口，--boot 在 import PySide6 之前分流
├── boot_agent.py          登录前守护进程（无 Qt）
├── core/
│   ├── backends/colorful.py   七彩虹 HID 后端
│   ├── backends/openrgb.py    OpenRGB SDK 后端
│   ├── engine.py              渲染循环 + 推送队列
│   ├── effects.py             25 种灯效
│   ├── fans.py                Super I/O 风扇与温度
│   ├── autostart.py           自启管理（注册表 / 计划任务）
│   └── config.py              配置持久化（原子写）
├── ui/                    界面（PySide6）
├── third_party/lhm/       LibreHardwareMonitor 运行时（需自行获取）
├── build.spec             PyInstaller 配置
└── install.iss            Inno Setup 安装脚本
```

---

## 致谢

- ARGB 协议逆向参考了 [nollie/chinese-motherboard-signalrgb-plugin](https://gitlab.com/nollie/chinese-motherboard-signalrgb-plugin)
- 风扇与传感器访问基于 [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
- 内核级 I/O 由 [PawnIO](https://github.com/namazso/PawnIO) 提供

---

## 许可证

本项目源码采用 [MIT](LICENSE)。第三方组件各自遵循其原始许可证，详见 LICENSE 文件末尾。
