"""Reconhecimento de voz (STT) offline via faster-whisper.

A classe carrega o modelo na primeira chamada (lazy) para acelerar a inicialização
do app. O modelo é mantido em memória e reutilizado entre chamadas.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class STTConfig:
    engine: str = "faster-whisper"
    model_size: str = "small"
    device: str = "auto"  # "auto" | "cpu" | "cuda"
    compute_type: str = "int8"  # int8 | int8_float16 | float16 | float32
    beam_size: int = 1
    vad_filter: bool = True
    language: str = "pt"

    @classmethod
    def from_dict(cls, data: dict, language: str = "pt") -> "STTConfig":
        return cls(
            engine=str(data.get("engine", "faster-whisper")),
            model_size=str(data.get("model_size", "small")),
            device=str(data.get("device", "auto")),
            compute_type=str(data.get("compute_type", "int8")),
            beam_size=int(data.get("beam_size", 1)),
            vad_filter=bool(data.get("vad_filter", True)),
            language=language,
        )


class STTError(RuntimeError):
    pass


class SpeechToText:
    """Wrapper estável em volta do faster-whisper."""

    def __init__(self, config: STTConfig):
        self.config = config
        self._model = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ model
    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel  # importação tardia
        except ImportError as exc:  # pragma: no cover
            raise STTError(
                "faster-whisper não está instalado. Rode `pip install -r requirements.txt`."
            ) from exc

        device = self.config.device
        if device == "auto":
            device = self._pick_device()

        logger.info(
            "Carregando faster-whisper modelo=%s device=%s compute=%s ...",
            self.config.model_size,
            device,
            self.config.compute_type,
        )
        t0 = time.monotonic()
        try:
            self._model = WhisperModel(
                self.config.model_size,
                device=device,
                compute_type=self.config.compute_type,
            )
        except Exception as exc:
            raise STTError(f"Falha ao carregar modelo Whisper: {exc}") from exc
        logger.info("Modelo carregado em %.1fs.", time.monotonic() - t0)

    @staticmethod
    def _pick_device() -> str:
        try:
            import torch  # type: ignore

            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    def warmup(self) -> None:
        """Pré-carrega o modelo (use em uma thread no boot para esconder a latência)."""
        with self._lock:
            self._load_model()

    # ------------------------------------------------------------------ transcribe
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcreve um array float32 mono. Retorna ``""`` se nada útil for detectado."""
        if audio.size == 0:
            return ""

        # faster-whisper espera 16 kHz mono float32
        if sample_rate != 16000:
            audio = self._resample(audio, sample_rate, 16000)

        with self._lock:
            self._load_model()
            assert self._model is not None
            try:
                segments, info = self._model.transcribe(
                    audio,
                    language=self.config.language,
                    beam_size=self.config.beam_size,
                    vad_filter=self.config.vad_filter,
                    condition_on_previous_text=False,
                )
                text_parts = [seg.text for seg in segments]
            except Exception as exc:
                logger.exception("Falha na transcrição: %s", exc)
                return ""

        text = " ".join(part.strip() for part in text_parts).strip()
        if text:
            logger.info("STT (%.2fs detectados): %r", info.duration, text)
        return text

    @staticmethod
    def _resample(audio: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
        """Resample linear simples — adequado para fala."""
        if sr_in == sr_out or audio.size == 0:
            return audio
        ratio = sr_out / sr_in
        new_len = int(round(audio.size * ratio))
        x_old = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
        return np.interp(x_new, x_old, audio).astype(np.float32)
