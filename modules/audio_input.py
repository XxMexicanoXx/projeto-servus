"""Captura de áudio do microfone com VAD por energia (RMS).

Usa ``sounddevice`` (PortAudio) para abrir um stream contínuo. Cada frase falada
é detectada por nível de energia: começamos a gravar quando o RMS ultrapassa o
limiar e fechamos quando temos ``silence_duration_seconds`` consecutivos abaixo
do limiar. Frases muito curtas são descartadas; frases muito longas são cortadas
em ``max_phrase_seconds`` para evitar travamento.

A classe expõe um ``Iterator[np.ndarray]`` thread-safe via ``listen()``.
"""

from __future__ import annotations

import collections
import queue
import threading
import time
from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    device_index: Optional[int] = None
    silence_threshold_rms: float = 0.012
    silence_duration_seconds: float = 0.8
    max_phrase_seconds: float = 12.0
    min_phrase_seconds: float = 0.4
    pre_roll_seconds: float = 0.3
    block_seconds: float = 0.05  # 50 ms blocks

    @classmethod
    def from_dict(cls, data: dict) -> "AudioConfig":
        return cls(
            sample_rate=int(data.get("sample_rate", 16000)),
            channels=int(data.get("channels", 1)),
            device_index=data.get("device_index"),
            silence_threshold_rms=float(data.get("silence_threshold_rms", 0.012)),
            silence_duration_seconds=float(data.get("silence_duration_seconds", 0.8)),
            max_phrase_seconds=float(data.get("max_phrase_seconds", 12.0)),
            min_phrase_seconds=float(data.get("min_phrase_seconds", 0.4)),
            pre_roll_seconds=float(data.get("pre_roll_seconds", 0.3)),
        )


class MicrophoneError(RuntimeError):
    """Falha ao abrir/usar o microfone."""


class AudioInput:
    """Captura áudio em frases delimitadas por silêncio.

    Use como context manager ou chame ``start()``/``stop()`` manualmente.
    """

    def __init__(self, config: AudioConfig):
        self.config = config
        self._block_size = max(1, int(config.sample_rate * config.block_seconds))
        self._block_queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=200)
        self._stream = None
        self._running = False
        self._paused = threading.Event()
        self._paused.set()  # set = listening, clear = paused
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._running:
            return
        try:
            import sounddevice as sd  # importação tardia (pesa)
        except ImportError as exc:  # pragma: no cover
            raise MicrophoneError(
                "sounddevice não está instalado. Rode `pip install -r requirements.txt`."
            ) from exc

        try:
            self._stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype="float32",
                blocksize=self._block_size,
                device=self.config.device_index,
                callback=self._on_block,
            )
            self._stream.start()
        except Exception as exc:  # sounddevice levanta vários tipos
            raise MicrophoneError(f"Falha ao abrir microfone: {exc}") from exc

        self._running = True
        logger.info(
            "Microfone aberto (rate=%d, channels=%d, device=%s)",
            self.config.sample_rate,
            self.config.channels,
            self.config.device_index,
        )

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception as exc:  # pragma: no cover
            logger.warning("Erro fechando stream de áudio: %s", exc)
        self._stream = None
        # esvazia fila
        try:
            while True:
                self._block_queue.get_nowait()
        except queue.Empty:
            pass
        logger.info("Microfone fechado.")

    def __enter__(self) -> "AudioInput":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # ------------------------------------------------------------------ control
    def pause(self) -> None:
        """Para de produzir frases (mas mantém o stream aberto)."""
        with self._lock:
            self._paused.clear()
            logger.info("Escuta pausada.")

    def resume(self) -> None:
        with self._lock:
            self._paused.set()
            logger.info("Escuta retomada.")

    def is_paused(self) -> bool:
        return not self._paused.is_set()

    # ------------------------------------------------------------------ stream
    def _on_block(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("sounddevice status: %s", status)
        try:
            mono = indata[:, 0] if indata.ndim > 1 else indata
            self._block_queue.put_nowait(mono.copy())
        except queue.Full:
            # Fila cheia significa que o consumidor travou; descartamos o bloco
            # mais antigo para manter latência sob controle.
            try:
                self._block_queue.get_nowait()
                self._block_queue.put_nowait(mono.copy())
            except queue.Empty:
                pass

    # ------------------------------------------------------------------ listen
    def listen(self) -> Iterator[np.ndarray]:
        """Itera sobre frases (np.ndarray float32) detectadas por VAD.

        O loop só termina quando ``stop()`` é chamado.
        """
        if not self._running:
            raise MicrophoneError("AudioInput.start() não foi chamado.")

        cfg = self.config
        threshold = cfg.silence_threshold_rms
        silence_blocks_target = max(1, int(cfg.silence_duration_seconds / cfg.block_seconds))
        max_phrase_blocks = max(1, int(cfg.max_phrase_seconds / cfg.block_seconds))
        min_phrase_blocks = max(1, int(cfg.min_phrase_seconds / cfg.block_seconds))
        pre_roll_blocks = max(0, int(cfg.pre_roll_seconds / cfg.block_seconds))

        pre_roll: collections.deque = collections.deque(maxlen=pre_roll_blocks)
        recording: list[np.ndarray] = []
        silence_count = 0
        in_phrase = False

        while self._running:
            try:
                block = self._block_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not self._paused.is_set():
                pre_roll.clear()
                recording.clear()
                in_phrase = False
                silence_count = 0
                continue

            rms = float(np.sqrt(np.mean(block * block) + 1e-12))

            if not in_phrase:
                pre_roll.append(block)
                if rms >= threshold:
                    in_phrase = True
                    recording = list(pre_roll)
                    recording.append(block)
                    silence_count = 0
            else:
                recording.append(block)
                if rms < threshold:
                    silence_count += 1
                else:
                    silence_count = 0

                ended_by_silence = silence_count >= silence_blocks_target
                ended_by_length = len(recording) >= max_phrase_blocks

                if ended_by_silence or ended_by_length:
                    if len(recording) >= min_phrase_blocks:
                        phrase = np.concatenate(recording).astype(np.float32)
                        logger.debug(
                            "Frase capturada: %.2fs (silêncio=%s len=%s)",
                            len(phrase) / cfg.sample_rate,
                            ended_by_silence,
                            ended_by_length,
                        )
                        yield phrase
                    recording = []
                    pre_roll.clear()
                    in_phrase = False
                    silence_count = 0

        return


def list_input_devices() -> list[dict]:
    """Lista dispositivos de entrada disponíveis (útil para configuração)."""
    try:
        import sounddevice as sd
    except ImportError:
        return []
    devices = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            devices.append(
                {
                    "index": idx,
                    "name": dev.get("name"),
                    "channels": dev.get("max_input_channels"),
                    "default_sample_rate": dev.get("default_samplerate"),
                }
            )
    return devices


if __name__ == "__main__":  # diagnóstico rápido
    import sys

    from utils.logger import setup_logging

    setup_logging("DEBUG")
    if "--list" in sys.argv:
        for d in list_input_devices():
            print(d)
        sys.exit(0)

    cfg = AudioConfig()
    with AudioInput(cfg) as audio:
        print("Fale algo (Ctrl+C para sair)...")
        try:
            for i, phrase in enumerate(audio.listen()):
                print(f"  frase #{i}: {len(phrase) / cfg.sample_rate:.2f}s, rms={np.sqrt(np.mean(phrase**2)):.4f}")
                if i >= 5:
                    break
        except KeyboardInterrupt:
            pass
