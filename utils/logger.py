"""Configuração centralizada de logging.

Usa um RotatingFileHandler em ``%LOCALAPPDATA%/VozAssistente/logs/`` (Windows)
ou ``~/.voz-assistente/logs/`` em outros sistemas, mais um StreamHandler em stderr.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _default_log_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "VozAssistente" / "logs"
    return Path.home() / ".voz-assistente" / "logs"


def setup_logging(
    level: str = "INFO",
    log_dir: Optional[str] = None,
    log_file_name: str = "assistant.log",
    max_bytes: int = 1_000_000,
    backup_count: int = 3,
) -> Path:
    """Inicializa o logging global.

    Idempotente: chamadas repetidas não duplicam handlers.

    Retorna o caminho do arquivo de log para conveniência.
    """
    global _configured

    log_path_dir = Path(log_dir) if log_dir else _default_log_dir()
    try:
        log_path_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_path_dir = Path.home()
    log_file = log_path_dir / log_file_name

    root = logging.getLogger()
    if _configured:
        root.setLevel(getattr(logging, level.upper(), logging.INFO))
        return log_file

    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    stream_handler = logging.StreamHandler(stream=sys.stderr)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        root.warning("Falha ao abrir arquivo de log %s: %s", log_file, exc)

    _configured = True
    return log_file


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger nomeado. Garante que ``setup_logging`` foi chamado."""
    if not _configured:
        setup_logging()
    return logging.getLogger(name)
