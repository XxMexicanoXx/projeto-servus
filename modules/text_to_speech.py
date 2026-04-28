"""Síntese de voz (TTS) offline com suporte a múltiplos engines.

Engines suportados, em ordem de preferência:

1. **Piper TTS** (``engine="piper"`` ou ``"auto"``): voz neural, alta qualidade,
   modelos ONNX leves (~30–60 MB). Voz padrão pt-BR masculina ``faber``.
2. **pyttsx3 / SAPI5** (``engine="pyttsx3"`` ou fallback): voz robótica do
   Windows. Fallback automático se Piper falhar.

A engine roda numa thread dedicada (``runAndWait`` / playback bloqueia).
Callbacks ``on_speak_start`` / ``on_speak_end`` permitem pausar a captura de
áudio durante a fala (evita o assistente "se ouvir" e gerar loop).
"""

from __future__ import annotations

import os
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TTSConfig:
    """Configuração do TTS.

    ``engine``: ``"auto"`` (default — tenta piper, cai pra pyttsx3), ``"piper"``,
    ou ``"pyttsx3"``.

    ``piper_model``: caminho para o ``.onnx`` da voz Piper. Se ``None``, busca em
    ``%APPDATA%/VozAssistente/voices/`` ou ``<dir do exe>/voices/``.

    ``voice_substrings``: lista ordenada de substrings para escolher a voz no
    fallback pyttsx3 (default: prefere Daniel — masculina pt-BR).
    """

    engine: str = "auto"
    rate: int = 185
    volume: float = 1.0
    piper_model: Optional[str] = None
    piper_speaker_id: Optional[int] = None
    voice_substrings: List[str] = field(
        default_factory=lambda: ["daniel", "portuguese (brazil)", "portuguese", "pt-br", "pt_br"]
    )

    @classmethod
    def from_dict(cls, data: dict) -> "TTSConfig":
        # aceita "voice_substring" (singular, legado) ou "voice_substrings" (lista)
        subs_raw = data.get("voice_substrings") or data.get("voice_substring")
        if subs_raw is None:
            subs = ["daniel", "portuguese (brazil)", "portuguese", "pt-br", "pt_br"]
        elif isinstance(subs_raw, str):
            subs = [subs_raw]
        else:
            subs = [str(s) for s in subs_raw]

        return cls(
            engine=str(data.get("engine", "auto")).lower(),
            rate=int(data.get("rate", 185)),
            volume=float(data.get("volume", 1.0)),
            piper_model=data.get("piper_model"),
            piper_speaker_id=data.get("piper_speaker_id"),
            voice_substrings=subs,
        )


_SENTINEL = object()


class _BaseEngine:
    name = "base"

    def synthesize_and_play(self, text: str) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        pass


class _PiperEngine(_BaseEngine):
    """Wrapper Piper TTS — síntese ONNX local de alta qualidade."""

    name = "piper"

    def __init__(self, model_path: Path, volume: float, speaker_id: Optional[int]):
        from piper.voice import PiperVoice  # type: ignore

        self._voice = PiperVoice.load(str(model_path))
        self._volume = max(0.0, min(1.0, volume))
        self._speaker_id = speaker_id
        self._sample_rate = int(self._voice.config.sample_rate)
        logger.info(
            "TTS Piper carregado: %s (sr=%d, num_speakers=%s)",
            model_path.name,
            self._sample_rate,
            getattr(self._voice.config, "num_speakers", "?"),
        )

    def synthesize_and_play(self, text: str) -> None:
        import numpy as np  # type: ignore
        import sounddevice as sd  # type: ignore

        kwargs: dict = {}
        if self._speaker_id is not None:
            kwargs["speaker_id"] = self._speaker_id

        try:
            chunks = list(self._voice.synthesize_stream_raw(text, **kwargs))
        except TypeError:
            chunks = list(self._voice.synthesize_stream_raw(text))

        if not chunks:
            logger.warning("Piper não gerou áudio para texto vazio/curto.")
            return

        raw = b"".join(chunks)
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if self._volume != 1.0:
            samples = samples * self._volume

        sd.play(samples, samplerate=self._sample_rate, blocking=True)


class _Pyttsx3Engine(_BaseEngine):
    """Fallback SAPI5 via pyttsx3."""

    name = "pyttsx3"

    def __init__(self, rate: int, volume: float, voice_substrings: List[str]):
        import pyttsx3  # type: ignore

        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", rate)
        self._engine.setProperty("volume", max(0.0, min(1.0, volume)))
        self._select_voice(voice_substrings)
        logger.info("TTS pyttsx3 pronto (rate=%d, volume=%.2f)", rate, volume)

    def _select_voice(self, substrings: List[str]) -> None:
        try:
            voices = list(self._engine.getProperty("voices"))
        except Exception as exc:
            logger.warning("Erro listando vozes pyttsx3: %s", exc)
            return

        def voice_blob(v) -> str:
            return " ".join(
                str(getattr(v, attr, "") or "") for attr in ("id", "name", "languages")
            ).lower()

        for sub in substrings:
            sub_low = sub.lower().strip()
            if not sub_low:
                continue
            for voice in voices:
                if sub_low in voice_blob(voice):
                    try:
                        self._engine.setProperty("voice", voice.id)
                        logger.info("Voz TTS selecionada: %s (match='%s')", voice.name, sub)
                        return
                    except Exception as exc:
                        logger.warning("Falha ao definir voz %s: %s", voice.name, exc)
        logger.warning(
            "Nenhuma voz pyttsx3 casou com substrings %s — usando padrão do sistema.",
            substrings,
        )

    def synthesize_and_play(self, text: str) -> None:
        self._engine.say(text)
        self._engine.runAndWait()

    def stop(self) -> None:
        try:
            self._engine.stop()
        except Exception:
            pass


def _piper_search_paths(explicit: Optional[str]) -> List[Path]:
    paths: List[Path] = []
    if explicit:
        paths.append(Path(os.path.expandvars(os.path.expanduser(explicit))))

    # %APPDATA%/VozAssistente/voices/
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            paths.append(Path(appdata) / "VozAssistente" / "voices")
    paths.append(Path.home() / ".config" / "voz-assistente" / "voices")

    # Pasta voices ao lado do exe (PyInstaller frozen) ou do projeto
    import sys

    if getattr(sys, "frozen", False):
        paths.append(Path(sys.executable).resolve().parent / "voices")
        paths.append(Path(getattr(sys, "_MEIPASS", "")) / "voices")
    else:
        paths.append(Path(__file__).resolve().parent.parent / "voices")

    return paths


def _resolve_piper_model(explicit: Optional[str]) -> Optional[Path]:
    """Acha o arquivo ``.onnx`` da voz Piper no sistema."""
    for p in _piper_search_paths(explicit):
        if p.is_file() and p.suffix == ".onnx":
            return p
        if p.is_dir():
            for candidate in sorted(p.glob("*.onnx")):
                json_side = candidate.with_suffix(".onnx.json")
                if json_side.exists():
                    return candidate
    return None


class TextToSpeech:
    """Fila de fala não-bloqueante.

    Cada chamada ``speak(text)`` enfileira a frase e retorna imediatamente.
    Callbacks ``on_speak_start`` / ``on_speak_end`` (se setados) são chamados
    no início/fim de cada frase — útil para pausar a captura de áudio.
    """

    def __init__(self, config: TTSConfig):
        self.config = config
        self._queue: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._engine: Optional[_BaseEngine] = None
        self._running = False
        self._init_lock = threading.Lock()
        self.on_speak_start: Optional[Callable[[], None]] = None
        self.on_speak_end: Optional[Callable[[], None]] = None

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
        if self._engine is not None:
            self._engine.stop()

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
        engine_pref = (self.config.engine or "auto").lower()

        # tenta Piper primeiro (a menos que pyttsx3 explicitamente)
        if engine_pref in ("auto", "piper"):
            model = _resolve_piper_model(self.config.piper_model)
            if model is not None:
                try:
                    self._engine = _PiperEngine(
                        model_path=model,
                        volume=self.config.volume,
                        speaker_id=self.config.piper_speaker_id,
                    )
                    return True
                except ImportError:
                    logger.info("piper-tts não instalado; tentando pyttsx3.")
                except Exception as exc:
                    logger.exception("Falha inicializando Piper: %s — tentando pyttsx3.", exc)
            else:
                logger.info(
                    "Modelo Piper (.onnx) não encontrado nas pastas-padrão; "
                    "tentando pyttsx3."
                )
            if engine_pref == "piper":
                # usuário pediu piper explicitamente, mas falhou — não cai pro 3
                logger.error("Engine 'piper' indisponível e fallback desabilitado.")
                return False

        if engine_pref in ("auto", "pyttsx3"):
            try:
                self._engine = _Pyttsx3Engine(
                    rate=self.config.rate,
                    volume=self.config.volume,
                    voice_substrings=self.config.voice_substrings,
                )
                return True
            except ImportError:
                logger.error("pyttsx3 não está instalado.")
            except Exception as exc:
                logger.exception("Falha inicializando pyttsx3: %s", exc)

        return False

    def _safe_callback(self, cb: Optional[Callable[[], None]], label: str) -> None:
        if cb is None:
            return
        try:
            cb()
        except Exception:
            logger.exception("Erro em callback %s", label)

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
        logger.info("TTS engine ativa: %s", self._engine.name)
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

            text = str(item)
            self._safe_callback(self.on_speak_start, "on_speak_start")
            try:
                self._engine.synthesize_and_play(text)
            except RuntimeError as exc:
                logger.warning("RuntimeError no TTS, reinicializando engine: %s", exc)
                try:
                    self._engine.stop()
                except Exception:
                    pass
                if not self._init_engine():
                    self._safe_callback(self.on_speak_end, "on_speak_end")
                    break
            except Exception:
                logger.exception("Erro inesperado no TTS")
                time.sleep(0.3)
            finally:
                self._safe_callback(self.on_speak_end, "on_speak_end")
