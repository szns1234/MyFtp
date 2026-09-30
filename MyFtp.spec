# -*- mode: python ; coding: utf-8 -*-
"""MyFtp PyInstaller 打包配置

本项目仅使用 Python 标准库（tkinter、ftplib 等），无需第三方依赖。
"""

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'core',
        'core.config_manager',
        'core.ftp_client',
        'core.file_monitor',
        'gui',
        'gui.app',
        'gui.msgbox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MyFtp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # GUI程序，不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,           # 如有图标可设为 'icon.ico'
)
