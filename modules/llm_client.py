"""Cliente LLM unificado para classificação de intents.

Suporta provedores OpenAI-compatíveis (Groq, OpenAI, OpenRouter) e Ollama local.
Default: **Groq** (gratuito, rápido, requer ``GROQ_API_KEY``).

Uso pelo IntentParser quando o regex não casar: o LLM retorna JSON estruturado
``{"intent": "abrir_programa", "slots": {"programa": "chrome"}}``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

LOGGER = logging.getLogger(__name__)


_INTENT_LIST = (
    "abrir_programa, fechar_programa, criar_pasta, criar_arquivo, "
    "deletar_pasta, deletar_arquivo, mover, desligar_computador, "
    "reiniciar_computador, cancelar_desligamento, buscar_web, digitar, "
    "volume, sair_assistente, pausar_escuta, saudacao, que_horas, "
    "que_data, mudar_nome, qual_meu_nome, desconhecido"
)


SYSTEM_PROMPT = f"""Você é um classificador de intents para um assistente pessoal por voz em português brasileiro chamado VozAssistente.

Sua tarefa: ler a frase do usuário e responder SOMENTE com JSON no formato:
{{"intent": "<nome>", "slots": {{...}}, "resposta": "<frase curta opcional para o assistente falar>"}}

Intents válidos: {_INTENT_LIST}.

Slots conhecidos por intent:
- abrir_programa / fechar_programa: "programa" (string, ex: "chrome", "bloco de notas")
- criar_pasta / deletar_pasta: "pasta" (string, nome da pasta)
- criar_arquivo / deletar_arquivo: "arquivo" (string, nome com extensão se possível)
- mover: "origem" e "destino" (strings)
- buscar_web: "query" (string)
- digitar: "texto" (string)
- volume: "raw" (a frase original)
- mudar_nome: "nome" (string capitalizada)

Regras:
- Se a frase for muito curta, ininteligível ou ruído (ex: "parabéns", "comentar", "obrigado"), retorne "desconhecido" SEM resposta.
- O Whisper às vezes transcreve errado — interprete com bom senso (ex: "arvre" pode ser "abrir").
- "Resposta" é opcional: deixe em branco se a ação já fala sozinha (ex: que_horas).
- Saudações curtas: responda algo natural em "resposta".
- NÃO invente intents fora da lista acima.

Exemplos:
"abre o chrome pra mim" -> {{"intent": "abrir_programa", "slots": {{"programa": "chrome"}}}}
"cria uma pasta nova chamada férias" -> {{"intent": "criar_pasta", "slots": {{"pasta": "férias"}}}}
"que horas são" -> {{"intent": "que_horas", "slots": {{}}}}
"obrigado" -> {{"intent": "desconhecido", "slots": {{}}}}
"oi tudo bem" -> {{"intent": "saudacao", "slots": {{}}, "resposta": "Tudo ótimo, e com você?"}}
"""


@dataclass
class LLMConfig:
    provider: str = "groq"  # groq | openai | openrouter | ollama
    endpoint: Optional[str] = None
    model: str = "llama-3.1-8b-instant"
    api_key: Optional[str] = None
    api_key_env: str = "GROQ_API_KEY"
    timeout_seconds: float = 10.0

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "LLMConfig":
        data = data or {}
        return cls(
            provider=str(data.get("provider", "groq")).lower(),
            endpoint=data.get("endpoint"),
            model=str(data.get("model", "llama-3.1-8b-instant")),
            api_key=data.get("api_key"),
            api_key_env=str(data.get("api_key_env", "GROQ_API_KEY")),
            timeout_seconds=float(data.get("timeout_seconds", 10.0)),
        )

    def resolve_api_key(self) -> Optional[str]:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            v = os.environ.get(self.api_key_env)
            if v:
                return v
        return None

    def resolve_endpoint(self) -> str:
        if self.endpoint:
            return self.endpoint.rstrip("/")
        return {
            "groq": "https://api.groq.com/openai/v1",
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "ollama": "http://localhost:11434",
        }.get(self.provider, "https://api.groq.com/openai/v1")


@dataclass
class LLMResult:
    intent: str
    slots: dict
    response: Optional[str] = None
    raw: Optional[str] = None


class LLMClient:
    """Wrapper sobre HTTP — sem dependências pesadas, usa ``requests``."""

    def __init__(self, config: LLMConfig):
        self.config = config

    def is_configured(self) -> bool:
        if self.config.provider == "ollama":
            return True
        return self.config.resolve_api_key() is not None

    def classify(self, text: str) -> Optional[LLMResult]:
        if not text or not text.strip():
            return None
        if not self.is_configured():
            return None
        try:
            if self.config.provider in ("groq", "openai", "openrouter"):
                return self._classify_openai_compat(text)
            if self.config.provider == "ollama":
                return self._classify_ollama(text)
            LOGGER.warning("Provedor LLM desconhecido: %s", self.config.provider)
            return None
        except Exception as exc:
            LOGGER.warning("LLM falhou: %s", exc)
            return None

    # ------------------------------------------------------------------ providers
    def _classify_openai_compat(self, text: str) -> Optional[LLMResult]:
        import requests  # type: ignore

        url = f"{self.config.resolve_endpoint()}/chat/completions"
        api_key = self.config.resolve_api_key()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 200,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.config.timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return self._parse_content(content)

    def _classify_ollama(self, text: str) -> Optional[LLMResult]:
        import requests  # type: ignore

        url = f"{self.config.resolve_endpoint()}/api/chat"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "format": "json",
        }
        resp = requests.post(url, json=payload, timeout=self.config.timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        return self._parse_content(content)

    @staticmethod
    def _parse_content(content: str) -> Optional[LLMResult]:
        try:
            obj = json.loads(content)
        except json.JSONDecodeError:
            LOGGER.debug("Resposta LLM não é JSON: %r", content[:200])
            return None
        intent = obj.get("intent")
        if not intent:
            return None
        return LLMResult(
            intent=str(intent),
            slots=dict(obj.get("slots") or {}),
            response=(obj.get("resposta") or obj.get("response") or None),
            raw=content,
        )
