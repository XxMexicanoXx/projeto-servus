"""Carregamento e validação do arquivo ``config.json``.

A pesquisa do arquivo segue esta ordem:
1. Argumento explícito ``path``
2. Variável de ambiente ``VOZ_ASSISTENTE_CONFIG``
3. ``%APPDATA%/VozAssistente/config.json`` (Windows — config do usuário,
   editável; é onde o instalador grava a cópia inicial)
4. ``./config.json`` ao lado do executável (modo portátil)
5. ``./assistant/config.json`` (modo dev)
6. Default embutido
"""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    "general": {
        "language": "pt",
        "log_level": "INFO",
        "start_listening_on_launch": True,
        "show_tray_icon": True,
        "exit_phrases": ["sair do assistente", "encerrar assistente", "fechar assistente"],
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "device_index": None,
        "silence_threshold_rms": 0.012,
        "silence_duration_seconds": 0.8,
        "max_phrase_seconds": 12.0,
        "min_phrase_seconds": 0.4,
        "pre_roll_seconds": 0.3,
    },
    "stt": {
        "engine": "faster-whisper",
        "model_size": "small",
        "device": "auto",
        "compute_type": "int8",
        "beam_size": 1,
        "vad_filter": True,
    },
    "tts": {
        "engine": "pyttsx3",
        "rate": 185,
        "volume": 1.0,
        "voice_substring": "portuguese",
    },
    "intents": {
        "confidence_threshold": 0.55,
        "use_llm_fallback": False,
    },
    "llm": {
        "provider": "ollama",
        "endpoint": "http://localhost:11434",
        "model": "llama3.1:8b-instruct-q4_K_M",
        "timeout_seconds": 30,
    },
    "actions": {
        "programs": {
            "chrome": "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "bloco de notas": "notepad.exe",
            "notepad": "notepad.exe",
            "calculadora": "calc.exe",
            "explorador": "explorer.exe",
            "spotify": "%APPDATA%/Spotify/Spotify.exe"
        },
        "default_folder": "%USERPROFILE%/Documents/Assistente",
        "allow_shutdown": True,
        "shutdown_delay_seconds": 30,
        "allow_keyboard_automation": True,
    },
    "wake_word": {
        "enabled": False,
        "phrase": "jarvis",
    },
}


class ConfigError(RuntimeError):
    """Erro ao carregar/validar o config."""


def _executable_dir() -> Path:
    """Diretório do executável real (compatível com PyInstaller onefile)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _user_config_dir() -> Optional[Path]:
    """Diretório do config do usuário (gravável)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "VozAssistente"
        return None
    return Path.home() / ".config" / "voz-assistente"


def _candidate_paths(explicit: Optional[str]) -> list[Path]:
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit).expanduser())
    env = os.environ.get("VOZ_ASSISTENTE_CONFIG")
    if env:
        paths.append(Path(env).expanduser())
    user_dir = _user_config_dir()
    if user_dir is not None:
        paths.append(user_dir / "config.json")
    exe_dir = _executable_dir()
    paths.append(exe_dir / "config.json")
    paths.append(exe_dir / "assistant" / "config.json")
    return paths


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Carrega o config.json (ou o default embutido)."""
    for candidate in _candidate_paths(path):
        if candidate.is_file():
            try:
                with candidate.open("r", encoding="utf-8") as fh:
                    user_cfg = json.load(fh)
                logger.info("Config carregado de %s", candidate)
                return _deep_merge(DEFAULT_CONFIG, user_cfg)
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("Falha ao ler %s: %s", candidate, exc)

    logger.warning("Nenhum config.json encontrado; usando defaults embutidos.")
    return deepcopy(DEFAULT_CONFIG)


def expand_path(value: str) -> str:
    """Expande variáveis de ambiente e ``~`` em uma string de caminho."""
    return os.path.expandvars(os.path.expanduser(value))
