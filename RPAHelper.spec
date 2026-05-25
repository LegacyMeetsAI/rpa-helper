# -*- mode: python ; coding: utf-8 -*-
"""RPA Helper 的 PyInstaller 打包配置。

只构建浏览器自动化版本（一文件夹，one-folder），不再包含 OCR 或桌面
自动化相关依赖。一文件夹模式的好处：
  - 启动快（无需把 Chromium 解压到 TEMP）；
  - 体积可控，最终用户也能直接看到 _internal/ 里的 Playwright 资源。

Author: huaiqing.wang
"""

import sys
from PyInstaller.utils.hooks import collect_all


# PyInstaller 静态分析抓不到的隐式依赖：Playwright 自身是懒加载的。
hiddenimports = [
    "playwright",
    "playwright.sync_api",
    "playwright._impl._driver",
    "playwright._impl._transport",
    "greenlet",
    "pyee",
]

# Playwright 自带 Node 驱动，需要把驱动二进制一并收集进来。
try:
    _pw_datas, _pw_binaries, _pw_hidden = collect_all("playwright")
    hiddenimports += _pw_hidden
except Exception as exc:
    sys.stderr.write(f"[spec] warning: failed to collect playwright: {exc}\n")
    _pw_datas = []
    _pw_binaries = []

# 把 config/ 目录里的种子文件一起带上（最终用户的流程文件会在 exe 旁边创建）。
datas = [
    ("rpa_helper/config", "rpa_helper/config"),
]
datas += _pw_datas

binaries = []
binaries += _pw_binaries


block_cipher = None

a = Analysis(
    ["rpa_helper/main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除明确用不到的大包，控制 dist 体积。
        "tkinter",
        "matplotlib",
        "notebook",
        "IPython",
        "pytest",
        "numpy",
        "cv2",
        "PIL",
        "keyboard",
        "mouse",
        "pyperclip",
        "pyscreeze",
        "mss",
        "paddleocr",
        "paddle",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RPAHelper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RPAHelper",
)
