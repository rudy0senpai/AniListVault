# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/Rudy0senpai/T450/goto/git/AniListVault/build/installer_stub/setup_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/Rudy0senpai/T450/goto/git/AniListVault/build/installer_stub/payload.zip', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'animevault'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AnimeVault-Setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/Rudy0senpai/T450/goto/git/AniListVault/src/animevault/resources/media/app.ico'],
)
