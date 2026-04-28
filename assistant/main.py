"""Ponto de entrada do assistente.

Orquestra:
- carregamento do config
- inicialização do logger
- threads de áudio + STT + intent + ação + TTS
- ícone de bandeja (system tray) com menu

Uso:
    python -m assistant.main           # modo dev (a partir da raiz do repo)
    python assistant/main.py           # alternativa
    VozAssistente.exe                  # após build com PyInstaller
"""

from __future__ import annotations

import argparse
import os
import queue
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# Permite executar `python assistant/main.py` direto do checkout
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from modules.action_executor import ActionConfig, ActionExecutor  # noqa: E402
from modules.audio_input import AudioConfig, AudioInput, MicrophoneError  # noqa: E402
from modules.intent_parser import IntentParser  # noqa: E402
from modules.onboarding import (  # noqa: E402
    run_onboarding_if_needed,
    request_groq_api_key,
)
from modules.wake_word import WakeWordMatcher  # noqa: E402
from modules.speech_to_text import SpeechToText, STTConfig, STTError  # noqa: E402
from modules.text_to_speech import TextToSpeech, TTSConfig  # noqa: E402
from modules.user_profile import UserProfile, load_profile, save_profile  # noqa: E402
from utils.config import load_config  # noqa: E402
from utils.logger import get_logger, setup_logging  # noqa: E402

APP_NAME = "VozAssistente"


class AssistantState:
    """Estados possíveis exibidos na bandeja."""

    IDLE = "parado"
    LISTENING = "ouvindo"
    PROCESSING = "processando"
    SPEAKING = "falando"
    ERROR = "erro"


class Assistant:
    """Orquestrador principal."""

    def __init__(self, config: dict, profile: Optional[UserProfile] = None):
        self.config = config
        self.logger = get_logger(__name__)
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._state = AssistantState.IDLE
        self._tray = None  # pystray.Icon, lazy
        self.profile = profile or UserProfile()

        self.audio = AudioInput(AudioConfig.from_dict(config.get("audio", {})))
        self.stt = SpeechToText(
            STTConfig.from_dict(
                config.get("stt", {}),
                language=config.get("general", {}).get("language", "pt"),
            )
        )
        self.tts = TextToSpeech(TTSConfig.from_dict(config.get("tts", {})))
        # Pausa a escuta enquanto o assistente fala — evita auto-feedback.
        self.tts.on_speak_start = self.audio.pause_for_tts
        self.tts.on_speak_end = self.audio.resume_from_tts

        self.parser = IntentParser(
            confidence_threshold=float(
                config.get("intents", {}).get("confidence_threshold", 0.55)
            ),
            use_llm_fallback=bool(
                config.get("intents", {}).get("use_llm_fallback", False)
            ),
            llm_config=config.get("llm", {}),
        )
        self.executor = ActionExecutor(
            ActionConfig.from_dict(config.get("actions", {})),
            on_request_exit=self.request_exit,
            on_request_pause=self.toggle_listen,
            user_profile=self.profile,
            on_profile_changed=self._save_profile,
        )

        self._exit_phrases = [
            phrase.lower().strip()
            for phrase in config.get("general", {}).get("exit_phrases", [])
        ]

        wake_cfg = config.get("wake_word", {}) or {}
        self._wake = WakeWordMatcher(
            phrase=str(wake_cfg.get("phrase", "servus")),
            enabled=bool(wake_cfg.get("enabled", True)),
            require_prefix=bool(wake_cfg.get("require_prefix", False)),
            extra_aliases=tuple(wake_cfg.get("aliases", []) or ()),
        )
        self._beep_on_capture = bool(
            config.get("general", {}).get("beep_on_capture", True)
        )

    def _save_profile(self) -> None:
        try:
            save_profile(self.profile)
        except Exception:
            self.logger.exception("Falha salvando perfil do usuário")

    # ------------------------------------------------------------------ state
    def _set_state(self, state: str) -> None:
        with self._state_lock:
            if self._state == state:
                return
            self._state = state
        self.logger.debug("Estado -> %s", state)
        self._update_tray_title()

    def get_state(self) -> str:
        with self._state_lock:
            return self._state

    # ------------------------------------------------------------------ run
    def run(self) -> int:
        self.logger.info("Iniciando %s ...", APP_NAME)

        # warmup do modelo Whisper em background para esconder a latência
        threading.Thread(target=self._safe_warmup_stt, name="stt-warmup", daemon=True).start()

        self.tts.start()

        try:
            self.audio.start()
        except MicrophoneError as exc:
            self.logger.error("Microfone indisponível: %s", exc)
            self.tts.speak_blocking(
                "Não consegui acessar o microfone. Verifique as permissões.",
                timeout=10,
            )
            return 2

        try:
            self.audio.run_mic_diagnostic(seconds=1.0)
        except Exception:
            self.logger.exception("Falha no diagnóstico de microfone (não-fatal).")

        if not self.config.get("general", {}).get("start_listening_on_launch", True):
            self.audio.pause()

        self._install_signal_handlers()

        worker = threading.Thread(target=self._listen_loop, name="listen-loop", daemon=True)
        worker.start()

        greeting_name = self.profile.display_name
        wake_hint = ""
        if self._wake.enabled:
            wake_hint = f" Diga {self._wake.phrase} antes de cada comando."
        if greeting_name:
            self.tts.speak(f"Olá {greeting_name}, assistente pronto.{wake_hint}")
        else:
            self.tts.speak(f"Assistente pronto.{wake_hint}")

        if self.config.get("general", {}).get("show_tray_icon", True):
            self._run_tray_blocking()  # bloqueia na main thread (requirement do pystray)
        else:
            try:
                while not self._stop_event.is_set():
                    self._stop_event.wait(timeout=0.5)
            except KeyboardInterrupt:
                pass

        self.shutdown()
        worker.join(timeout=2.0)
        return 0

    def _safe_warmup_stt(self) -> None:
        try:
            self.stt.warmup()
        except STTError as exc:
            self.logger.error("Falha no warmup do STT: %s", exc)
            self._set_state(AssistantState.ERROR)

    # ------------------------------------------------------------------ loop
    def _listen_loop(self) -> None:
        sample_rate = self.audio.config.sample_rate
        try:
            for phrase in self.audio.listen():
                if self._stop_event.is_set():
                    break
                self._set_state(AssistantState.PROCESSING)
                try:
                    text = self.stt.transcribe(phrase, sample_rate=sample_rate)
                except Exception as exc:
                    self.logger.exception("Erro inesperado no STT: %s", exc)
                    text = ""
                if not text:
                    self._set_state(
                        AssistantState.LISTENING
                        if not self.audio.is_paused()
                        else AssistantState.IDLE
                    )
                    continue
                self._handle_text(text)
                self._set_state(
                    AssistantState.LISTENING
                    if not self.audio.is_paused()
                    else AssistantState.IDLE
                )
        except Exception:
            self.logger.exception("listen-loop morreu")
            self._set_state(AssistantState.ERROR)

    def _handle_text(self, text: str) -> None:
        self.logger.info("Frase capturada: %r", text)
        if self._beep_on_capture:
            self.audio.play_capture_beep()

        lowered = text.lower().strip()
        for phrase in self._exit_phrases:
            if phrase and phrase in lowered:
                self.tts.speak("Encerrando o assistente.")
                self.request_exit()
                return

        if self._wake.enabled:
            stripped = self._wake.match(text)
            if stripped is None:
                self.logger.info("Wake word ausente em %r — ignorando.", text)
                return
            text = stripped
            self.logger.info("Wake word detectada; comando: %r", text)

        if not text.strip():
            self.tts.speak("Sim?")
            return

        intent = self.parser.parse(text)
        if intent is None:
            return
        response = self.executor.execute(intent)
        if response:
            self._set_state(AssistantState.SPEAKING)
            self.tts.speak(response)

    # ------------------------------------------------------------------ control
    def toggle_listen(self) -> None:
        if self.audio.is_paused():
            self.audio.resume()
            self._set_state(AssistantState.LISTENING)
            self.tts.speak("Escuta retomada.")
        else:
            self.audio.pause()
            self._set_state(AssistantState.IDLE)
            self.tts.speak("Escuta pausada.")

    def request_exit(self) -> None:
        if self._stop_event.is_set():
            return
        self.logger.info("Pedido de encerramento recebido.")
        self._stop_event.set()
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass

    def shutdown(self) -> None:
        self.logger.info("Encerrando %s ...", APP_NAME)
        try:
            self.audio.stop()
        except Exception:
            self.logger.exception("Erro fechando áudio")
        try:
            self.tts.stop()
        except Exception:
            self.logger.exception("Erro fechando TTS")

    # ------------------------------------------------------------------ signals
    def _install_signal_handlers(self) -> None:
        def _handler(signum, frame):
            self.logger.info("Sinal %s recebido.", signum)
            self.request_exit()

        try:
            signal.signal(signal.SIGINT, _handler)
            signal.signal(signal.SIGTERM, _handler)
        except (ValueError, OSError):
            # signals só funcionam na main thread; ignorar em casos especiais
            pass

    # ------------------------------------------------------------------ tray
    def _run_tray_blocking(self) -> None:
        try:
            import pystray  # type: ignore
            from PIL import Image, ImageDraw  # type: ignore
        except ImportError:
            self.logger.warning(
                "pystray/Pillow não instalados; rodando sem ícone de bandeja."
            )
            try:
                while not self._stop_event.is_set():
                    self._stop_event.wait(timeout=0.5)
            except KeyboardInterrupt:
                pass
            return

        image = self._make_tray_image(Image, ImageDraw)

        def _on_toggle(icon, item):
            self.toggle_listen()

        def _on_exit(icon, item):
            self.request_exit()

        def _listen_label(item):
            return "Pausar escuta" if not self.audio.is_paused() else "Iniciar escuta"

        def _status_label(item):
            return f"Status: {self.get_state()}"

        menu = pystray.Menu(
            pystray.MenuItem(_status_label, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_listen_label, _on_toggle, default=True),
            pystray.MenuItem("Sair", _on_exit),
        )

        self._tray = pystray.Icon(APP_NAME, image, APP_NAME, menu)
        # estado inicial
        self._set_state(
            AssistantState.LISTENING if not self.audio.is_paused() else AssistantState.IDLE
        )
        try:
            self._tray.run()
        except Exception:
            self.logger.exception("Erro no loop do tray")

    def _update_tray_title(self) -> None:
        if self._tray is None:
            return
        try:
            self._tray.title = f"{APP_NAME} — {self._state}"
            # força refresh do menu (status label)
            try:
                self._tray.update_menu()
            except Exception:
                pass
        except Exception:
            pass

    @staticmethod
    def _make_tray_image(Image, ImageDraw):
        size = 64
        img = Image.new("RGBA", (size, size), (30, 30, 30, 255))
        draw = ImageDraw.Draw(img)
        # microfone estilizado
        draw.rounded_rectangle((22, 12, 42, 38), radius=8, fill=(0, 200, 255, 255))
        draw.rectangle((30, 38, 34, 50), fill=(0, 200, 255, 255))
        draw.line((20, 50, 44, 50), fill=(0, 200, 255, 255), width=3)
        return img


# --------------------------------------------------------------------------- cli
def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Assistente pessoal por voz pt-BR")
    parser.add_argument("--config", help="Caminho para um config.json customizado")
    parser.add_argument("--log-level", default=None, help="DEBUG/INFO/WARNING/ERROR")
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Lista dispositivos de áudio de entrada e sai.",
    )
    parser.add_argument("--no-tray", action="store_true", help="Não exibe ícone de bandeja.")
    parser.add_argument(
        "--skip-onboarding",
        action="store_true",
        help="Pula o diálogo de boas-vindas (útil para debug).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    log_level = (
        args.log_level
        or config.get("general", {}).get("log_level", "INFO")
    )
    log_path = setup_logging(level=log_level)
    logger = get_logger(__name__)
    logger.info("Logs em %s", log_path)

    if args.list_devices:
        from modules.audio_input import list_input_devices

        for dev in list_input_devices():
            print(dev)
        return 0

    if args.no_tray:
        config.setdefault("general", {})["show_tray_icon"] = False

    profile = load_profile()
    if not args.skip_onboarding:
        try:
            profile = run_onboarding_if_needed(profile)
        except Exception:
            logger.exception("Erro durante onboarding — seguindo sem nome.")

        # Pede a chave do Groq se ainda não houver e o LLM estiver habilitado
        try:
            llm_cfg = config.get("llm", {}) or {}
            api_key_env = llm_cfg.get("api_key_env", "GROQ_API_KEY")
            already = bool(llm_cfg.get("api_key")) or bool(os.environ.get(api_key_env))
            if (
                config.get("intents", {}).get("use_llm_fallback", False)
                and not already
                and not profile.skip_groq_prompt
            ):
                key = request_groq_api_key()
                if key:
                    from utils.config import save_user_config_field

                    save_user_config_field(["llm", "api_key"], key)
                    config.setdefault("llm", {})["api_key"] = key
                    logger.info("Chave Groq salva em %%APPDATA%%/VozAssistente/config.json")
                else:
                    profile.skip_groq_prompt = True
                    save_profile(profile)
        except Exception:
            logger.exception("Falha pedindo chave da API do Groq (não-fatal).")

    assistant = Assistant(config, profile=profile)
    return assistant.run()


if __name__ == "__main__":
    sys.exit(main())
