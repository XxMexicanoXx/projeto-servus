"""Interpretação de comandos por voz em intents estruturados.

Estratégia em camadas:
1. Normalização do texto (lower, sem acento, sem pontuação)
2. Regras determinísticas por regex (rápidas e precisas para frases comuns)
3. (Opcional) Fallback para um LLM local (Ollama) — desativado por padrão

Cada regra retorna um ``Intent`` com ``name`` e ``slots``. O ``ActionExecutor``
consome os intents e executa as ações.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Pattern

from utils.logger import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- data
@dataclass
class Intent:
    name: str
    slots: dict = field(default_factory=dict)
    confidence: float = 1.0
    raw_text: str = ""

    def __repr__(self) -> str:  # pragma: no cover
        return f"Intent({self.name!r}, slots={self.slots}, conf={self.confidence:.2f})"


@dataclass
class _Rule:
    name: str
    pattern: Pattern[str]
    extractor: Callable[[re.Match], dict]
    confidence: float = 0.95


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # preserva ``.`` (extensões de arquivo) e ``/`` (caminhos); remove o resto
    text = re.sub(r"[^\w\s./]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# --------------------------------------------------------------------------- rules
def _build_rules() -> List[_Rule]:
    rules: List[_Rule] = []

    # --- abrir <programa>
    rules.append(
        _Rule(
            name="abrir_programa",
            pattern=re.compile(
                r"^(?:por favor\s+)?(?:abr(?:ir|a|e|i|am)|inici(?:ar|a|e)|execut(?:ar|a|e)|lig(?:ar|a|ue))\s+(?:o\s+|a\s+)?(?P<programa>.+?)$"
            ),
            extractor=lambda m: {"programa": m.group("programa").strip()},
        )
    )

    # --- sair do assistente (precedência sobre fechar_programa)
    rules.append(
        _Rule(
            name="sair_assistente",
            pattern=re.compile(
                r"^(?:sair|encerr(?:ar|a|e)|fech(?:ar|a|e)|finaliz(?:ar|a|e))"
                r"(?:\s+do)?\s+assistente$"
            ),
            extractor=lambda m: {},
        )
    )

    # --- pausar/retomar escuta (precedência sobre fechar_programa)
    rules.append(
        _Rule(
            name="pausar_escuta",
            pattern=re.compile(
                r"^(?:paus(?:ar|a|e)|silenci(?:ar|a|e))\s+(?:a\s+)?escuta$"
            ),
            extractor=lambda m: {},
        )
    )

    # --- fechar <programa>
    rules.append(
        _Rule(
            name="fechar_programa",
            pattern=re.compile(
                r"^(?:fech(?:ar|a|e|ai)|encerr(?:ar|a|e|ai)|mat(?:ar|a|e|ai))\s+(?:o\s+|a\s+)?(?P<programa>.+?)$"
            ),
            extractor=lambda m: {"programa": m.group("programa").strip()},
        )
    )

    # --- criar pasta chamada X
    rules.append(
        _Rule(
            name="criar_pasta",
            pattern=re.compile(
                r"^(?:cri(?:ar|a|e)|nov[ao])\s+(?:uma?\s+)?pasta(?:\s+chamada)?\s+(?P<nome>.+?)$"
            ),
            extractor=lambda m: {"nome": m.group("nome").strip()},
        )
    )

    # --- criar arquivo chamado X
    rules.append(
        _Rule(
            name="criar_arquivo",
            pattern=re.compile(
                r"^(?:cri(?:ar|a|e)|nov[ao])\s+(?:um\s+)?arquivo(?:\s+chamado)?\s+(?P<nome>.+?)$"
            ),
            extractor=lambda m: {"nome": m.group("nome").strip()},
        )
    )

    _verbo_apagar = (
        r"(?:delet(?:ar|a|e)|apag(?:ar|a|ue|ar)|remov(?:er|a|e)|exclu(?:ir|a|i))"
    )

    # --- deletar/apagar pasta X
    rules.append(
        _Rule(
            name="deletar_pasta",
            pattern=re.compile(
                rf"^{_verbo_apagar}\s+(?:a\s+)?pasta\s+(?P<nome>.+?)$"
            ),
            extractor=lambda m: {"nome": m.group("nome").strip()},
        )
    )

    # --- deletar/apagar arquivo X
    rules.append(
        _Rule(
            name="deletar_arquivo",
            pattern=re.compile(
                rf"^{_verbo_apagar}\s+(?:o\s+)?arquivo\s+(?P<nome>.+?)$"
            ),
            extractor=lambda m: {"nome": m.group("nome").strip()},
        )
    )

    # --- mover X para Y
    rules.append(
        _Rule(
            name="mover",
            pattern=re.compile(
                r"^(?:mov(?:er|a|e))\s+(?P<origem>.+?)\s+para\s+(?P<destino>.+?)$"
            ),
            extractor=lambda m: {
                "origem": m.group("origem").strip(),
                "destino": m.group("destino").strip(),
            },
        )
    )

    # --- desligar / reiniciar
    rules.append(
        _Rule(
            name="desligar_computador",
            pattern=re.compile(r"^desliga(?:r|)\s+(?:o\s+)?(?:computador|pc|maquina)$"),
            extractor=lambda m: {},
        )
    )
    rules.append(
        _Rule(
            name="reiniciar_computador",
            pattern=re.compile(r"^reinicia(?:r|)\s+(?:o\s+)?(?:computador|pc|maquina)$"),
            extractor=lambda m: {},
        )
    )
    rules.append(
        _Rule(
            name="cancelar_desligamento",
            pattern=re.compile(r"^(?:cancela(?:r|)|abort(?:ar|a|e))\s+(?:o\s+)?desligamento$"),
            extractor=lambda m: {},
        )
    )

    # --- buscar na web
    rules.append(
        _Rule(
            name="buscar_web",
            pattern=re.compile(
                r"^(?:pesquis(?:ar|a|e)|busc(?:ar|a|ue)|googl(?:ar|a|e))\s+(?:por\s+)?(?P<query>.+?)$"
            ),
            extractor=lambda m: {"query": m.group("query").strip()},
        )
    )

    # --- digitar X
    rules.append(
        _Rule(
            name="digitar",
            pattern=re.compile(
                r"^(?:digit(?:ar|a|e)|escrev(?:er|a|e))\s+(?P<texto>.+?)$"
            ),
            extractor=lambda m: {"texto": m.group("texto").strip()},
        )
    )

    # --- volume
    rules.append(
        _Rule(
            name="volume",
            pattern=re.compile(
                r"^(?:aument(?:ar|a|e)|diminui(?:r|)|abaix(?:ar|a|e)|sub(?:ir|a|i))\s+(?:o\s+)?volume$"
            ),
            extractor=lambda m: {"raw": m.group(0)},
            confidence=0.7,
        )
    )

    # --- saudação simples
    rules.append(
        _Rule(
            name="saudacao",
            pattern=re.compile(
                r"^(?:oi|ola|hey|salve|bom dia|boa tarde|boa noite|tudo bem)(?:\s+.*)?$"
            ),
            extractor=lambda m: {},
            confidence=0.6,
        )
    )

    # --- horas / data
    rules.append(
        _Rule(
            name="que_horas",
            pattern=re.compile(r"^(?:que\s+horas?(?:\s+sao)?|me\s+diga\s+as\s+horas)$"),
            extractor=lambda m: {},
        )
    )
    rules.append(
        _Rule(
            name="que_data",
            pattern=re.compile(r"^(?:que\s+(?:dia|data)\s+(?:e\s+hoje|hoje)?|me\s+diga\s+a\s+data)$"),
            extractor=lambda m: {},
            confidence=0.85,
        )
    )

    # --- mudar nome do usuário
    rules.append(
        _Rule(
            name="mudar_nome",
            pattern=re.compile(
                r"^(?:meu\s+nome\s+e|me\s+chamo|pode\s+me\s+chamar\s+de|"
                r"mud(?:e|a|ar)\s+meu\s+nome\s+(?:para|pra)|"
                r"troc(?:a|ar|e)\s+meu\s+nome\s+(?:para|pra))\s+(?P<nome>[\w\-' ]{2,40}?)\s*\.?\s*$"
            ),
            extractor=lambda m: {"nome": m.group("nome").strip().title()},
            confidence=0.9,
        )
    )
    rules.append(
        _Rule(
            name="qual_meu_nome",
            pattern=re.compile(
                r"^(?:qual\s+(?:e\s+)?o?\s*meu\s+nome|"
                r"voce\s+sabe\s+(?:o\s+)?meu\s+nome|"
                r"como\s+(?:voce\s+)?me\s+cham[oa])\??$"
            ),
            extractor=lambda m: {},
            confidence=0.85,
        )
    )

    return rules


# --------------------------------------------------------------------------- parser
class IntentParser:
    """Combina regras determinísticas + LLM (Groq/OpenAI/Ollama) como fallback."""

    def __init__(
        self,
        confidence_threshold: float = 0.55,
        use_llm_fallback: bool = False,
        llm_config: Optional[dict] = None,
    ):
        self.confidence_threshold = confidence_threshold
        self.use_llm_fallback = use_llm_fallback
        self.llm_config = llm_config or {}
        self.rules = _build_rules()
        self._llm = None
        if self.use_llm_fallback:
            from .llm_client import LLMClient, LLMConfig

            self._llm = LLMClient(LLMConfig.from_dict(self.llm_config))
            if self._llm.is_configured():
                logger.info(
                    "LLM fallback habilitado: provider=%s model=%s",
                    self._llm.config.provider,
                    self._llm.config.model,
                )
            else:
                logger.warning(
                    "LLM fallback habilitado mas sem chave de API "
                    "(provider=%s, env=%s). Defina a chave no config ou variável de ambiente.",
                    self._llm.config.provider,
                    self._llm.config.api_key_env,
                )

    # ------------------------------------------------------------------ public
    def parse(self, text: str) -> Optional[Intent]:
        if not text or not text.strip():
            return None
        norm = _normalize(text)
        logger.debug("intent normalize: %r -> %r", text, norm)

        for rule in self.rules:
            match = rule.pattern.match(norm)
            if match is not None:
                try:
                    slots = rule.extractor(match)
                except Exception as exc:
                    logger.warning("Erro extraindo slots da regra %s: %s", rule.name, exc)
                    continue
                if rule.confidence < self.confidence_threshold:
                    continue
                return Intent(
                    name=rule.name,
                    slots=slots,
                    confidence=rule.confidence,
                    raw_text=text,
                )

        if self._llm is not None and self._llm.is_configured():
            result = self._llm.classify(text)
            if result is not None and result.intent and result.intent != "desconhecido":
                logger.info("LLM intent: %s slots=%s", result.intent, result.slots)
                return Intent(
                    name=result.intent,
                    slots={**result.slots, "_llm_response": result.response} if result.response else dict(result.slots),
                    confidence=0.7,
                    raw_text=text,
                )

        return Intent(name="desconhecido", slots={"raw": text}, confidence=0.0, raw_text=text)
