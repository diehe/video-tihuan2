# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path.cwd()
OPENSSL_LIB = Path("/opt/homebrew/opt/openssl@3/lib")
EXTRA_DATAS = []
if (OPENSSL_LIB / "libssl.3.dylib").exists():
    EXTRA_DATAS.append((str((OPENSSL_LIB / "libssl.3.dylib").resolve()), "."))
if (OPENSSL_LIB / "libcrypto.3.dylib").exists():
    EXTRA_DATAS.append((str((OPENSSL_LIB / "libcrypto.3.dylib").resolve()), "."))


a = Analysis(
    [str(ROOT / "engine" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=EXTRA_DATAS,
    hiddenimports=["engine.simple_server", "engine.file_dialog", "engine.pipeline", "engine.schemas"],
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
    a.binaries,
    a.datas,
    [],
    name="video-tihuan-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
