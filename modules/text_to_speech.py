"""Síntese de voz (TTS) offline via pyttsx3 com fila não-bloqueante.

pyttsx3 usa SAPI5 no Windows. A engine é mantida numa thread dedicada porque
``runAndWait()`` bloqueia, e queremos que o resto do assistente continue rodando
(escutando, processando, etc.) enquanto o áudio toca.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TTSConfig:
    engine: str = "pyttsx3"
    rate: int = 185
    volume: float = 1.0
    voice_substring: str = "portuguese"

    @classmethod
    def from_dict(cls, data: dict) -> "TTSConfig":
        return cls(
            engine=str(data.get("engine", "pyttsx3")),
            rate=int(data.get("rate", 185)),
            volume=float(data.get("volume", 1.0)),
            voice_substring=str(data.get("voice_substring", "portuguese")),
        )


_SENTINEL = object()


class TextToSpeech:
    """Fila de fala não-bloqueante.

    Cada chamada ``speak(text)`` enfileira a frase e retorna imediatamente.
    """

    def __init__(self, config: TTSConfig):
        self.config = config
        self._queue: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._engine = None
        self._running = False
        self._init_lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        with self._init_lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._worker, name="tts-worker", daemon=True
            )
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        if not self._running:
            return
        self._running = False
        self._queue.put(_SENTINEL)
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    # ------------------------------------------------------------------ public
    def speak(self, text: str) -> None:
        """Enfileira ``text`` para ser falado. Não bloqueia."""
        if not text or not text.strip():
            return
        if not self._running:
            self.start()
        self._queue.put(text)

    def speak_blocking(self, text: str, timeout: float = 30.0) -> None:
        """Versão que aguarda o término — útil em scripts."""
        if not text:
            return
        done = threading.Event()

        def _wait_marker():
            done.set()

        self.speak(text)
        self._queue.put(_wait_marker)
        done.wait(timeout=timeout)

    # ------------------------------------------------------------------ worker
    def _init_engine(self) -> bool:
        try:
            import pyttsx3  # type: ignore
        except ImportError:
            logger.error("pyttsx3 não está instalado.")
            return False

        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.config.rate)
            self._engine.setProperty("volume", max(0.0, min(1.0, self.config.volume)))
            self._select_voice()
            logger.info(
                "TTS pyttsx3 pronto (rate=%d, volume=%.2f)",
                self.config.rate,
                self.config.volume,
            )
            return True
        except Exception as exc:
            logger.exception("Falha inicializando pyttsx3: %s", exc)
            self._engine = None
            return False

    def _select_voice(self) -> None:
        if self._engine is None:
            return
        substring = self.config.voice_substring.lower().strip()
        if not substring:
            return
        try:
            for voice in self._engine.getProperty("voices"):
                blob = " ".join(
                    str(getattr(voice, attr, "") or "")
                    for attr in ("id", "name", "languages")
                ).lower()
                if substring in blob or "pt" in blob or "brazil" in blob:
                    self._engine.setProperty("voice", voice.id)
                    logger.info("Voz TTS selecionada: %s", voice.name)
                    return
            logger.warning(
                "Nenhuma voz contendo %r encontrada; usando voz padrão do sistema.",
                substring,
            )
        except Exception as exc:
            logger.warning("Erro selecionando voz TTS: %s", exc)

    def _worker(self) -> None:
        if not self._init_engine():
            # drena fila silenciosamente para não vazar memória
            while self._running:
                try:
                    item = self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if item is _SENTINEL:
                    return
            return

        assert self._engine is not None
        while self._running:
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is _SENTINEL:
                break
            if callable(item):
                try:
                    item()
                except Exception:
                    logger.exception("Erro em callback TTS")
                continue
            try:
                self._engine.say(str(item))
                self._engine.runAndWait()
            except RuntimeError as exc:
                # SAPI5 às vezes levanta "run loop already started"; reinicializa
                logger.warning("RuntimeError no TTS, reinicializando engine: %s", exc)
                try:
                    self._engine.stop()
                except Exception:
                    pass
                if not self._init_engine():
                    break
            except Exception:
                logger.exception("Erro inesperado no TTS")
                time.sleep(0.5)
