# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['snekbooru\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('graphics', 'graphics'), ('snekbooru\\lngpcks', 'snekbooru\\lngpcks'), ('snekbooru\\vendor', 'snekbooru\\vendor')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5.QtBluetooth', 'PyQt5.QtNfc', 'PyQt5.QtLocation', 'PyQt5.QtSensors', 'PyQt5.QtXmlPatterns', 'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtTest', 'PyQt5.QtSql', 'tkinter', 'IPython', 'jedi'],
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
    name='Snekbooru',
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
    icon=['git_graphics/S.png'],
)
