# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os
import shutil


ROOT = Path.cwd()
OPENSSL_LIB = Path("/opt/homebrew/opt/openssl@3/lib")
EXTRA_DATAS = []
EXTRA_BINARIES = []
if (OPENSSL_LIB / "libssl.3.dylib").exists():
    EXTRA_DATAS.append((str((OPENSSL_LIB / "libssl.3.dylib").resolve()), "."))
if (OPENSSL_LIB / "libcrypto.3.dylib").exists():
    EXTRA_DATAS.append((str((OPENSSL_LIB / "libcrypto.3.dylib").resolve()), "."))


def _ffmpeg_candidates():
    candidates = []
    choco_root = Path(os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey"))
    choco_tools = choco_root / "lib" / "ffmpeg" / "tools"
    candidates.append(choco_root / "lib" / "ffmpeg" / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe")
    if choco_tools.exists():
        candidates.extend(sorted(choco_tools.glob("**/ffmpeg.exe")))
    found = shutil.which("ffmpeg.exe") or shutil.which("ffmpeg")
    if found:
        candidates.append(Path(found))
    return candidates


def _resolve_ffmpeg():
    for candidate in _ffmpeg_candidates():
        if candidate.exists():
            return str(candidate)
    return None


FFMPEG = _resolve_ffmpeg()
if FFMPEG:
    EXTRA_BINARIES.append((FFMPEG, "."))


a = Analysis(
    [str(ROOT / "engine" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=EXTRA_BINARIES,
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
