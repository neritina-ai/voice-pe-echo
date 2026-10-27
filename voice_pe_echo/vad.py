"""Voice activity detection.

Every detector takes one frame of 512 samples (32 ms) of 16 kHz, 16-bit, mono
PCM and returns the probability (0..1) that the frame contains speech. 512
samples is also the chunk size the Voice PE firmware sends, and the window size
Silero VAD requires.
"""

from __future__ import annotations

import logging
import math
from typing import Protocol

import numpy as np

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512
FRAME_BYTES = FRAME_SAMPLES * 2
FRAME_SECONDS = FRAME_SAMPLES / SAMPLE_RATE

_LOGGER = logging.getLogger(__name__)


class Vad(Protocol):
    name: str

    def __call__(self, frame: bytes) -> float: ...

    def reset(self) -> None: ...


def frame_dbfs(frame: bytes) -> float:
    """Return the RMS level of a PCM frame in dBFS (-100 for digital silence)."""
    samples = np.frombuffer(frame, dtype="<i2").astype(np.float32)
    if samples.size == 0:
        return -100.0
    rms = math.sqrt(float(np.mean(samples * samples))) / 32768.0
    if rms <= 1e-5:
        return -100.0
    return 20.0 * math.log10(rms)


class SileroVad:
    """Neural VAD (the same model Home Assistant's Assist uses)."""

    name = "silero"

    def __init__(self) -> None:
        from pysilero_vad import SileroVoiceActivityDetector

        self._detector = SileroVoiceActivityDetector()

    def __call__(self, frame: bytes) -> float:
        return self._detector(frame)

    def reset(self) -> None:
        self._detector.reset()


class EnergyVad:
    """Fallback VAD: a frame is speech when it is clearly louder than the noise floor.

    The noise floor follows quiet frames quickly and loud frames very slowly,
    so steady background noise (fans, air conditioning) is learned while a
    sentence is not.
    """

    name = "energy"

    def __init__(self, margin_db: float = 12.0, min_db: float = -55.0) -> None:
        self._margin_db = margin_db
        self._min_db = min_db
        self._noise_db: float | None = None

    def __call__(self, frame: bytes) -> float:
        level = frame_dbfs(frame)
        if self._noise_db is None:
            self._noise_db = level
        speech = level > max(self._noise_db + self._margin_db, self._min_db)
        if level < self._noise_db:
            self._noise_db += 0.2 * (level - self._noise_db)
        elif not speech:
            self._noise_db += 0.02 * (level - self._noise_db)
        else:
            self._noise_db += 0.001 * (level - self._noise_db)
        return 1.0 if speech else 0.0

    def reset(self) -> None:
        # Keep the learned noise floor: the room did not change.
        pass


def create_vad(kind: str = "auto") -> Vad:
    """Create a VAD by name: "silero", "energy" or "auto" (Silero when installed)."""
    if kind == "energy":
        return EnergyVad()
    try:
        return SileroVad()
    except ImportError:
        if kind == "silero":
            raise
        _LOGGER.warning("找不到 pysilero-vad，改用簡易音量偵測（準確度較低）")
        return EnergyVad()
