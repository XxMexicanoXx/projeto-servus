"""Perfil do usuário (nome / apelido) persistido em ``%APPDATA%``.

Mantemos esse perfil **separado** do ``config.json`` porque ``config.json`` é
configuração técnica do app (caminhos de programas, parâmetros de áudio) e o
perfil é dado do usuário final. Em upgrades, o perfil deve sempre persistir.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """Dados pessoais do usuário."""

    name: Optional[str] = None
    nickname: Optional[str] = None
    has_completed_onboarding: bool = False

    @property
    def display_name(self) -> Optional[str]:
        """Nome mais natural para usar nas respostas (apelido > nome)."""
        return (self.nickname or self.name or "").strip() or None


def profile_dir() -> Path:
    """Diretório onde gravamos o perfil (``%APPDATA%`` no Windows)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "VozAssistente"
    return Path.home() / ".config" / "voz-assistente"


def profile_path() -> Path:
    return profile_dir() / "user_profile.json"


def load_profile() -> UserProfile:
    path = profile_path()
    if not path.exists():
        return UserProfile()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return UserProfile(
            name=data.get("name"),
            nickname=data.get("nickname"),
            has_completed_onboarding=bool(data.get("has_completed_onboarding", False)),
        )
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Falha ao ler perfil em %s: %s — recriando.", path, exc)
        return UserProfile()


def save_profile(profile: UserProfile) -> None:
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(profile)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.info("Perfil salvo em %s", path)


_VALID_NAME_RE = re.compile(r"^[\wÀ-ÿ\s\-']{1,40}$", re.UNICODE)


def sanitize_name(value: str) -> Optional[str]:
    """Retorna ``value`` limpo, ou ``None`` se inválido."""
    if not value:
        return None
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None
    if len(cleaned) > 40:
        cleaned = cleaned[:40].rstrip()
    if not _VALID_NAME_RE.match(cleaned):
        return None
    return cleaned
