"""Detecção (fuzzy) de palavra-gatilho na transcrição.

Trabalha em cima da saída do Whisper, então não exige modelo extra.
Filtra alucinações ao ignorar frases que não contenham a palavra-gatilho —
mesmo com pequenas variações de transcrição (ex: "Servus" → "Servos",
"Service", "Cervos").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    text = _strip_accents(text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Variações comuns que o Whisper produz para "Servus".
_DEFAULT_ALIASES_BY_PHRASE = {
    "servus": ("servus", "servos", "service", "cervos", "cervus", "selvus", "ser vos"),
    "jarvis": ("jarvis", "jervis", "jarbis", "charles"),
    "computador": ("computador", "comput dor"),
    "assistente": ("assistente", "assist ente"),
}


@dataclass
class WakeWordMatcher:
    phrase: str = "servus"
    enabled: bool = True
    require_prefix: bool = False
    extra_aliases: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        base = _normalize(self.phrase)
        defaults = _DEFAULT_ALIASES_BY_PHRASE.get(base, (base,))
        merged: list[str] = []
        for raw in (*defaults, *self.extra_aliases, base):
            n = _normalize(raw)
            if n and n not in merged:
                merged.append(n)
        self._aliases = tuple(merged)

    @property
    def aliases(self) -> Tuple[str, ...]:
        return self._aliases

    def match(self, text: str) -> Optional[str]:
        """Retorna o comando após a wake word, ou None se ausente.

        - Se ``require_prefix=True``, a wake word precisa estar no início.
        - Caso contrário, aceita em qualquer posição: tudo antes é descartado,
          o restante é o comando.
        - Comparação ignora acentos e pontuação.
        """
        if not self.enabled:
            return text
        if not text:
            return None
        norm = _normalize(text)
        tokens = norm.split(" ")
        for i, tok in enumerate(tokens):
            if tok in self._aliases or any(tok.startswith(a) for a in self._aliases):
                if self.require_prefix and i != 0:
                    return None
                # Reconstrói o comando original a partir do índice (em texto original)
                return _restore_after_token(text, i + 1).strip()
            # Verifica bigramas (ex: "ser vos")
            if i + 1 < len(tokens):
                pair = f"{tok} {tokens[i + 1]}"
                if pair in self._aliases:
                    if self.require_prefix and i != 0:
                        return None
                    return _restore_after_token(text, i + 2).strip()
        return None


def _restore_after_token(text: str, token_index: int) -> str:
    """Devolve o texto original a partir do n-ésimo token (separado por espaços)."""
    parts = text.split()
    if token_index >= len(parts):
        return ""
    return " ".join(parts[token_index:])


def expand_aliases(phrase: str, extras: Iterable[str] = ()) -> Tuple[str, ...]:
    matcher = WakeWordMatcher(phrase=phrase, extra_aliases=tuple(extras))
    return matcher.aliases
