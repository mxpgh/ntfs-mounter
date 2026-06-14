# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['ntfs_mounter.py'],
    pathex=[],
    binaries=[],
    datas=[('icon_menubar.png', '.')],
    hiddenimports=['preferences', 'volume_monitor', 'mounter', 'ui'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'tcl', 'tk', '_tkinter',
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'PIL', 'cv2', 'tensorflow', 'torch',
        'multiprocessing', 'ctypes.test',
        'idlelib', 'pydoc', 'doctest', 'pdb',
        'asyncio', 'concurrent',
        'curses',
        'unittest', 'test',
        'ensurepip', 'pip', 'pkg_resources', 'setuptools',
    ],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NTFS Mounter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
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
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name='NTFS Mounter',
)
app = BUNDLE(
    coll,
    name='NTFS Mounter.app',
    icon='icon.icns',
    bundle_identifier='com.ntfs-mounter',
    info_plist={'LSUIElement': True, 'NSHighResolutionCapable': True},
)
