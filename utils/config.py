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

CONFIG_SCHEMA_VERSION = 3


DEFAULT_CONFIG: Dict[str, Any] = {
    "config_schema_version": CONFIG_SCHEMA_VERSION,
    "general": {
        "language": "pt",
        "log_level": "INFO",
        "start_listening_on_launch": True,
        "show_tray_icon": True,
        "beep_on_capture": True,
        "exit_phrases": ["sair do assistente", "encerrar assistente", "fechar assistente"],
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "device_index": None,
        "silence_threshold_rms": 0.02,
        "silence_duration_seconds": 0.9,
        "max_phrase_seconds": 12.0,
        "min_phrase_seconds": 0.35,
        "pre_roll_seconds": 0.3,
    },
    "stt": {
        "engine": "faster-whisper",
        "model_size": "base",
        "device": "auto",
        "compute_type": "int8",
        "beam_size": 1,
        "vad_filter": True,
        "initial_prompt": "Comandos para um assistente em português brasileiro.",
        "no_speech_threshold": 0.6,
        "log_probability_threshold": -1.0,
    },
    "tts": {
        "engine": "auto",
        "rate": 185,
        "volume": 1.0,
        "piper_model": None,
        "piper_speaker_id": None,
        "voice_substrings": ["daniel", "portuguese (brazil)", "portuguese", "pt-br", "pt_br"],
    },
    "intents": {
        "confidence_threshold": 0.55,
        "use_llm_fallback": True,
    },
    "llm": {
        "provider": "groq",
        "endpoint": None,
        "model": "llama-3.1-8b-instant",
        "api_key": None,
        "api_key_env": "GROQ_API_KEY",
        "timeout_seconds": 10,
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
        "enabled": True,
        "phrase": "servus",
        "require_prefix": False,
        "aliases": [],
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


def _migrate_legacy(user_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Atualiza configs antigos para o schema atual.

    Estratégia: para campos novos sensíveis (TTS engine='auto', wake_word, llm
    com Groq), forçamos os defaults se o config do usuário ainda estiver no
    schema antigo. Outros campos (paths de programas, threshold, voz singular)
    são preservados.
    """
    user_version = int(user_cfg.get("config_schema_version", 0) or 0)
    if user_version >= CONFIG_SCHEMA_VERSION:
        return user_cfg

    logger.info(
        "Migrando config schema v%d -> v%d", user_version, CONFIG_SCHEMA_VERSION
    )

    user_cfg = deepcopy(user_cfg)

    tts = user_cfg.setdefault("tts", {})
    legacy_voice = tts.pop("voice_substring", None)
    if legacy_voice and "voice_substrings" not in tts:
        tts["voice_substrings"] = [legacy_voice, "daniel", "portuguese (brazil)", "portuguese"]
    if tts.get("engine") in (None, "pyttsx3"):
        tts["engine"] = "auto"
    tts.setdefault("voice_substrings", DEFAULT_CONFIG["tts"]["voice_substrings"])

    user_cfg.setdefault("wake_word", deepcopy(DEFAULT_CONFIG["wake_word"]))

    llm = user_cfg.setdefault("llm", {})
    if llm.get("provider") in (None, "ollama") and "api_key" not in llm:
        for k, v in DEFAULT_CONFIG["llm"].items():
            llm.setdefault(k, v)
        llm["provider"] = "groq"

    intents = user_cfg.setdefault("intents", {})
    # Em schemas antigos (<3) o LLM era um hook não usado de fato. Forçamos
    # True na migração para que o usuário receba o benefício (o app pede a
    # chave Groq no onboarding e cai pra regex caso sem chave).
    intents["use_llm_fallback"] = True

    stt = user_cfg.setdefault("stt", {})
    if stt.get("model_size") == "small":
        stt["model_size"] = "base"
    stt.setdefault("initial_prompt", DEFAULT_CONFIG["stt"]["initial_prompt"])
    stt.setdefault("no_speech_threshold", DEFAULT_CONFIG["stt"]["no_speech_threshold"])
    stt.setdefault("log_probability_threshold", DEFAULT_CONFIG["stt"]["log_probability_threshold"])

    general = user_cfg.setdefault("general", {})
    general.setdefault("beep_on_capture", True)

    user_cfg["config_schema_version"] = CONFIG_SCHEMA_VERSION
    return user_cfg


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Carrega o config.json (ou o default embutido)."""
    for candidate in _candidate_paths(path):
        if candidate.is_file():
            try:
                with candidate.open("r", encoding="utf-8") as fh:
                    user_cfg = json.load(fh)
                logger.info("Config carregado de %s", candidate)
                user_cfg = _migrate_legacy(user_cfg)
                merged = _deep_merge(DEFAULT_CONFIG, user_cfg)

                # Persiste migração se rodou sobre o config do usuário
                if (
                    candidate.parent == _user_config_dir()
                    and merged.get("config_schema_version") != _user_schema_version_on_disk(candidate)
                ):
                    try:
                        with candidate.open("w", encoding="utf-8") as fh:
                            json.dump(merged, fh, indent=2, ensure_ascii=False)
                        logger.info("Config migrado e salvo em %s", candidate)
                    except OSError as exc:
                        logger.warning("Falha ao gravar config migrado: %s", exc)
                return merged
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("Falha ao ler %s: %s", candidate, exc)

    logger.warning("Nenhum config.json encontrado; usando defaults embutidos.")
    return deepcopy(DEFAULT_CONFIG)


def _user_schema_version_on_disk(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return int(json.load(fh).get("config_schema_version", 0) or 0)
    except Exception:
        return 0


def save_user_config_field(key_path: list[str], value: Any) -> Optional[Path]:
    """Atualiza/grava um campo aninhado no config do usuário em ``%APPDATA%``.

    Cria o arquivo se não existir, preservando os outros campos. Útil para
    persistir a chave Groq que o usuário cola no diálogo de onboarding.
    """
    user_dir = _user_config_dir()
    if user_dir is None:
        return None
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / "config.json"
    cfg: Dict[str, Any]
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, json.JSONDecodeError):
            cfg = {}
    else:
        cfg = {}
    node = cfg
    for k in key_path[:-1]:
        node = node.setdefault(k, {})
    node[key_path[-1]] = value
    cfg.setdefault("config_schema_version", CONFIG_SCHEMA_VERSION)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
    return path


def expand_path(value: str) -> str:
    """Expande variáveis de ambiente e ``~`` em uma string de caminho."""
    return os.path.expandvars(os.path.expanduser(value))
