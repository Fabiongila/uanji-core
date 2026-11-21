# -*- mode: python ; coding: utf-8 -*-
# Empacota o backend como pasta (onedir): arranque mais rápido do que onefile em hardware antigo.
# Uso: cd backend && .venv/bin/pyinstaller packaging/uanji-backend.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 (definido pelo PyInstaller)
sys.path.insert(0, ROOT)

hidden = (
    collect_submodules("uanji")
    + collect_submodules("uvicorn")
    + ["keyring.backends.macOS", "multipart", "python_multipart", "tzdata"]
)
try:
    import anthropic  # noqa: F401  (fornecedor de IA opcional)

    hidden += collect_submodules("anthropic")
except ImportError:
    pass

# Voz (opcional): Vosk (libvosk), PortAudio (sounddevice) e AVFoundation (permissões, vozes).
binaries = []
datas_voice = []
for pkg, mods in (("vosk", ["vosk"]), ("sounddevice", ["sounddevice", "_sounddevice"]), ("AVFoundation", ["AVFoundation", "objc"])):
    try:
        __import__(pkg)
    except ImportError:
        continue
    for m in mods:
        hidden += collect_submodules(m)
    binaries += collect_dynamic_libs(pkg)
    datas_voice += collect_data_files(pkg)
try:
    import _sounddevice_data  # noqa: F401

    datas_voice += collect_data_files("_sounddevice_data")
    binaries += collect_dynamic_libs("_sounddevice_data")
except ImportError:
    pass

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],  # noqa: F821
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "alembic"), "alembic"), (os.path.join(ROOT, "alembic.ini"), "."), *datas_voice],
    binaries=binaries,
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "mypy", "ruff", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="uanji-backend", console=True, target_arch="x86_64")
coll = COLLECT(exe, a.binaries, a.datas, name="uanji-backend")
