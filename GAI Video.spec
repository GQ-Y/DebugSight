# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('/Users/hook/py/VideoSj/icon.png', '.'), ('/Users/hook/py/VideoSj/ai_config.json', '.'), ('/Users/hook/py/VideoSj/prompt_templates.json', '.'), ('/Users/hook/py/VideoSj/settings.json', '.'), ('/Users/hook/py/VideoSj/src', 'src'), ('/Users/hook/py/VideoSj/utils.py', '.'), ('utils.py', '.')],
    hiddenimports=['src.db_handler', 'src.stream_manager', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'cv2', 'numpy', 'utils'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GAI Video',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['/Users/hook/py/VideoSj/icon.png'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GAI Video',
)
app = BUNDLE(
    coll,
    name='GAI Video.app',
    icon='/Users/hook/py/VideoSj/icon.png',
    bundle_identifier=None,
)
