"""Execução das ações associadas a cada intent.

Cada handler retorna uma string com a resposta verbal que o assistente deve
falar. O executor é tolerante a falhas: erros viram resposta de voz amigável.

Suporte multiplataforma básico para facilitar testes em Linux/macOS, mas o foco
é Windows (subprocess de .exe, ``shutdown /s``, etc.).
"""

from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import sys
import threading
import unicodedata
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

from utils.config import expand_path
from utils.logger import get_logger

from .intent_parser import Intent

logger = get_logger(__name__)

IS_WINDOWS = os.name == "nt"


@dataclass
class ActionConfig:
    programs: Dict[str, str]
    default_folder: str = "%USERPROFILE%/Documents/Assistente"
    allow_shutdown: bool = True
    shutdown_delay_seconds: int = 30
    allow_keyboard_automation: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "ActionConfig":
        return cls(
            programs={str(k): str(v) for k, v in (data.get("programs") or {}).items()},
            default_folder=str(data.get("default_folder", "%USERPROFILE%/Documents/Assistente")),
            allow_shutdown=bool(data.get("allow_shutdown", True)),
            shutdown_delay_seconds=int(data.get("shutdown_delay_seconds", 30)),
            allow_keyboard_automation=bool(data.get("allow_keyboard_automation", True)),
        )


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower().strip()


class ActionExecutor:
    """Despacha ``Intent`` -> handler -> resposta de voz."""

    def __init__(
        self,
        config: ActionConfig,
        on_request_exit: Optional[Callable[[], None]] = None,
        on_request_pause: Optional[Callable[[], None]] = None,
    ):
        self.config = config
        self._on_request_exit = on_request_exit
        self._on_request_pause = on_request_pause
        self._handlers: Dict[str, Callable[[Intent], str]] = {
            "abrir_programa": self._abrir_programa,
            "fechar_programa": self._fechar_programa,
            "criar_pasta": self._criar_pasta,
            "criar_arquivo": self._criar_arquivo,
            "deletar_pasta": self._deletar_pasta,
            "deletar_arquivo": self._deletar_arquivo,
            "mover": self._mover,
            "desligar_computador": self._desligar,
            "reiniciar_computador": self._reiniciar,
            "cancelar_desligamento": self._cancelar_desligamento,
            "buscar_web": self._buscar_web,
            "digitar": self._digitar,
            "volume": self._volume,
            "sair_assistente": self._sair_assistente,
            "pausar_escuta": self._pausar_escuta,
            "saudacao": self._saudacao,
            "que_horas": self._que_horas,
            "que_data": self._que_data,
            "desconhecido": self._desconhecido,
        }

    # ------------------------------------------------------------------ dispatch
    def execute(self, intent: Intent) -> str:
        handler = self._handlers.get(intent.name, self._desconhecido)
        try:
            response = handler(intent)
            logger.info("Intent %s -> %r", intent.name, response)
            return response
        except Exception as exc:
            logger.exception("Erro executando intent %s: %s", intent.name, exc)
            return "Ocorreu um erro ao executar o comando."

    # ------------------------------------------------------------------ helpers
    def _resolve_program(self, name: str) -> Optional[str]:
        key = _strip_accents(name)
        for cfg_name, cfg_path in self.config.programs.items():
            if _strip_accents(cfg_name) == key or key in _strip_accents(cfg_name):
                return expand_path(cfg_path)
        # último recurso: o próprio nome (assume que está no PATH)
        if shutil.which(name):
            return name
        return None

    def _resolve_default_folder(self) -> Path:
        folder = Path(expand_path(self.config.default_folder))
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def _safe_name(name: str) -> str:
        for ch in '<>:"|?*':
            name = name.replace(ch, "")
        return name.strip()

    # ------------------------------------------------------------------ handlers
    def _abrir_programa(self, intent: Intent) -> str:
        name = intent.slots.get("programa", "").strip()
        if not name:
            return "Qual programa você quer abrir?"
        target = self._resolve_program(name)
        if target is None:
            return f"Não encontrei o programa {name} no meu config."
        try:
            if IS_WINDOWS:
                subprocess.Popen(  # noqa: S603
                    [target] if target.lower().endswith(".exe") else target,
                    shell=not target.lower().endswith(".exe"),
                    creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
                )
            else:
                subprocess.Popen(  # noqa: S603,S607
                    ["xdg-open", target],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return f"Abrindo {name}."
        except FileNotFoundError:
            return f"O programa {name} não foi encontrado em {target}."
        except OSError as exc:
            logger.warning("Erro abrindo %s: %s", target, exc)
            return f"Não consegui abrir {name}."

    def _fechar_programa(self, intent: Intent) -> str:
        name = intent.slots.get("programa", "").strip()
        if not name:
            return "Qual programa devo fechar?"
        target = self._resolve_program(name) or name
        exe_name = Path(target).name
        if not exe_name.lower().endswith(".exe"):
            exe_name += ".exe" if IS_WINDOWS else ""
        try:
            if IS_WINDOWS:
                subprocess.run(  # noqa: S603,S607
                    ["taskkill", "/IM", exe_name, "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                subprocess.run(  # noqa: S603,S607
                    ["pkill", "-f", exe_name], check=False
                )
            return f"Fechando {name}."
        except OSError as exc:
            logger.warning("Erro fechando %s: %s", exe_name, exc)
            return f"Não consegui fechar {name}."

    def _criar_pasta(self, intent: Intent) -> str:
        nome = self._safe_name(intent.slots.get("nome", ""))
        if not nome:
            return "Qual o nome da pasta?"
        base = self._resolve_default_folder()
        target = base / nome
        target.mkdir(parents=True, exist_ok=True)
        return f"Pasta {nome} criada em {base}."

    def _criar_arquivo(self, intent: Intent) -> str:
        nome = self._safe_name(intent.slots.get("nome", ""))
        if not nome:
            return "Qual o nome do arquivo?"
        if "." not in nome:
            nome += ".txt"
        base = self._resolve_default_folder()
        target = base / nome
        target.touch(exist_ok=True)
        return f"Arquivo {nome} criado em {base}."

    def _deletar_pasta(self, intent: Intent) -> str:
        nome = self._safe_name(intent.slots.get("nome", ""))
        if not nome:
            return "Qual pasta devo deletar?"
        base = self._resolve_default_folder()
        target = base / nome
        if not target.exists():
            return f"Pasta {nome} não encontrada em {base}."
        if not target.is_dir():
            return f"{nome} não é uma pasta."
        shutil.rmtree(target)
        return f"Pasta {nome} deletada."

    def _deletar_arquivo(self, intent: Intent) -> str:
        nome = self._safe_name(intent.slots.get("nome", ""))
        if not nome:
            return "Qual arquivo devo deletar?"
        base = self._resolve_default_folder()
        target = base / nome
        if not target.exists():
            return f"Arquivo {nome} não encontrado em {base}."
        if not target.is_file():
            return f"{nome} não é um arquivo."
        target.unlink()
        return f"Arquivo {nome} deletado."

    def _mover(self, intent: Intent) -> str:
        origem = self._safe_name(intent.slots.get("origem", ""))
        destino = self._safe_name(intent.slots.get("destino", ""))
        if not origem or not destino:
            return "Preciso da origem e do destino para mover."
        base = self._resolve_default_folder()
        src = base / origem
        dst = base / destino
        if not src.exists():
            return f"{origem} não foi encontrado em {base}."
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Movido {origem} para {destino}."

    def _desligar(self, intent: Intent) -> str:
        if not self.config.allow_shutdown:
            return "O desligamento está desativado no config."
        delay = max(0, int(self.config.shutdown_delay_seconds))
        try:
            if IS_WINDOWS:
                subprocess.run(  # noqa: S603,S607
                    ["shutdown", "/s", "/t", str(delay)], check=True
                )
            else:
                subprocess.run(  # noqa: S603,S607
                    ["shutdown", "-h", f"+{max(1, delay // 60)}"], check=False
                )
            return (
                f"Desligando em {delay} segundos. Diga "
                f"'cancelar desligamento' para abortar."
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            logger.warning("Falha ao desligar: %s", exc)
            return "Não consegui agendar o desligamento."

    def _reiniciar(self, intent: Intent) -> str:
        if not self.config.allow_shutdown:
            return "O reinício está desativado no config."
        delay = max(0, int(self.config.shutdown_delay_seconds))
        try:
            if IS_WINDOWS:
                subprocess.run(  # noqa: S603,S607
                    ["shutdown", "/r", "/t", str(delay)], check=True
                )
            else:
                subprocess.run(  # noqa: S603,S607
                    ["shutdown", "-r", f"+{max(1, delay // 60)}"], check=False
                )
            return f"Reiniciando em {delay} segundos."
        except (OSError, subprocess.CalledProcessError) as exc:
            logger.warning("Falha ao reiniciar: %s", exc)
            return "Não consegui agendar o reinício."

    def _cancelar_desligamento(self, intent: Intent) -> str:
        try:
            if IS_WINDOWS:
                subprocess.run(["shutdown", "/a"], check=False)  # noqa: S603,S607
            else:
                subprocess.run(["shutdown", "-c"], check=False)  # noqa: S603,S607
            return "Desligamento cancelado."
        except OSError as exc:
            logger.warning("Falha ao cancelar desligamento: %s", exc)
            return "Não consegui cancelar o desligamento."

    def _buscar_web(self, intent: Intent) -> str:
        query = intent.slots.get("query", "").strip()
        if not query:
            return "O que você quer pesquisar?"
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        try:
            webbrowser.open(url, new=2)
            return f"Pesquisando por {query}."
        except Exception as exc:
            logger.warning("Falha abrindo navegador: %s", exc)
            return "Não consegui abrir o navegador."

    def _digitar(self, intent: Intent) -> str:
        if not self.config.allow_keyboard_automation:
            return "Automação de teclado desativada no config."
        texto = intent.slots.get("texto", "")
        if not texto:
            return "O que você quer que eu digite?"
        try:
            import pyautogui  # type: ignore

            pyautogui.typewrite(texto, interval=0.02)
            return "Pronto."
        except ImportError:
            return "pyautogui não está instalado."
        except Exception as exc:
            logger.warning("Falha digitando: %s", exc)
            return "Não consegui digitar."

    def _volume(self, intent: Intent) -> str:
        if not self.config.allow_keyboard_automation:
            return "Automação de teclado desativada no config."
        raw = _strip_accents(intent.slots.get("raw", ""))
        increase = any(w in raw for w in ("aument", "sub"))
        try:
            import pyautogui  # type: ignore

            key = "volumeup" if increase else "volumedown"
            for _ in range(5):
                pyautogui.press(key)
            return "Volume ajustado."
        except ImportError:
            return "pyautogui não está instalado."
        except Exception as exc:
            logger.warning("Falha ajustando volume: %s", exc)
            return "Não consegui ajustar o volume."

    def _sair_assistente(self, intent: Intent) -> str:
        if self._on_request_exit is not None:
            threading.Timer(0.5, self._on_request_exit).start()
        return "Encerrando o assistente. Até logo."

    def _pausar_escuta(self, intent: Intent) -> str:
        if self._on_request_pause is not None:
            self._on_request_pause()
            return "Escuta pausada."
        return "Não consigo pausar agora."

    def _saudacao(self, intent: Intent) -> str:
        return "Olá! Como posso ajudar?"

    def _que_horas(self, intent: Intent) -> str:
        now = datetime.datetime.now()
        return f"Agora são {now.strftime('%H horas e %M minutos')}."

    def _que_data(self, intent: Intent) -> str:
        now = datetime.datetime.now()
        meses = [
            "janeiro", "fevereiro", "março", "abril", "maio", "junho",
            "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
        ]
        return f"Hoje é {now.day} de {meses[now.month - 1]} de {now.year}."

    def _desconhecido(self, intent: Intent) -> str:
        raw = intent.slots.get("raw") or intent.raw_text
        logger.info("Intent desconhecido: %r", raw)
        return "Desculpe, não entendi o comando."
