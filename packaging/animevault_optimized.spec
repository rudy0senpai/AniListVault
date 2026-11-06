# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None


# QtWebEngine is 194+ MB and not used by the application.
# QtPdf is 180+ MB and not used by the application.
# PySide6-QtWebEngineCore and PySide6-QtPdf are the largest components.
EXCLUDE_MODULES = [
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtPdf",
    "PySide6.QtNetworkAuth",
    "PySide6.Qt3D",
    "PySide6.QtDataVisualization",
    "PySide6.QtOpenGL",
    "PySide6.QtQml",
    "PySide6.QtQml",
    "PySide6.QtCharts",
    "PySide6.QtConcurrent",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtWebChannel",
    "PySide6.QtWebView",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtNfc",
    "PySide6.QtBluetooth",
    "PySide6.QtMultimediaWidgets",
]

# Modules required by the application (explicit, to avoid collecting unused ones)
REQUIRED_MODULES = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtMultimedia",
]

# PyInstaller hooks (copied to avoid version conflicts)
a = Analysis(
    [os.path.join(os.path.dirname(__file__), "..", "src", "animevault", "cli.py")],
    pathex=["src"],
    binaries=[],
    hiddenimports=[
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDE_MODULES,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AnimeVault",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=os.path.join(os.path.dirname(__file__), "..", "src", "animevault", "resources", "media", "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="AnimeVault",
)
