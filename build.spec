# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件、无控制台、带图标。"""

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('app.ico', '.'),
        ('third_party/lhm', 'third_party/lhm'),
    ],
    hiddenimports=['hid', 'psutil', 'pythonnet', 'clr'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'numpy', 'PIL', 'matplotlib', 'scipy', 'pandas',
        'pytest', 'pip', 'sqlite3',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets',
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtMultimedia', 'PySide6.QtCharts', 'PySide6.Qt3DCore',
        'PySide6.QtDataVisualization', 'PySide6.QtPdf', 'PySide6.QtSql',
        'PySide6.QtTest', 'PySide6.QtBluetooth', 'PySide6.QtSerialPort',
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AuroraARGB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    # 让 exe 的清单声明 requireAdministrator：双击即提权，
    # 不再需要右键「以管理员身份运行」。风扇控制本来就需要管理员权限。
    uac_admin=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',
)
