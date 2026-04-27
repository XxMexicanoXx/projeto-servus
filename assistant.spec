# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — gera um único VozAssistente.exe (onefile) sem console.

Uso:
    pyinstaller assistant.spec --clean --noconfirm

Saída:
    dist/VozAssistente.exe
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


block_cipher = None
ROOT = Path(SPECPATH)


# faster-whisper (ctranslate2) precisa das DLLs nativas e dos arquivos do tokenizer
datas = []
binaries = []

datas += collect_data_files("faster_whisper")
binaries += collect_dynamic_libs("ctranslate2")
datas += collect_data_files("ctranslate2")

# config.json fica embutido no bundle como fallback; o usuário pode colocar
# um config.json ao lado do .exe para sobrescrever (ver utils/config.py).
datas += [(str(ROOT / "assistant" / "config.json"), "assistant")]

hidden_imports = [
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "pyttsx3.drivers.dummy",
    "pyttsx3.drivers.espeak",
    "pyttsx3.drivers.nsss",
    "comtypes.stream",
    "PIL._tkinter_finder",
    "pystray._win32",
]


a = Analysis(
    [str(ROOT / "assistant" / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "PyQt5",
        "PyQt6",
        "pandas",
        "torch",  # remova esta linha se quiser usar GPU via PyTorch
        "transformers",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VozAssistente",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # GUI app (sem janela de console)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                # opcional: caminho para um .ico
)
