"""Play recorded sentences on the PC's speakers."""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np

from .vad import SAMPLE_RATE

FADE_SECONDS = 0.01
NORMALIZE_PEAK = 0.89  # -1 dBFS
NORMALIZE_MAX_GAIN = 8.0  # +18 dB at most, so near-silence is not blown up


class PlayerError(Exception):
    pass


def _import_sounddevice() -> Any:
    try:
        import sounddevice
    except OSError as err:  # PortAudio shared library missing (Linux)
        raise PlayerError(
            "找不到 PortAudio 音效函式庫。Linux 請先執行：sudo apt install libportaudio2"
        ) from err
    return sounddevice


def list_output_devices() -> str:
    sd = _import_sounddevice()
    default_out = sd.default.device[1]
    lines = []
    for index, info in enumerate(sd.query_devices()):
        if info["max_output_channels"] <= 0:
            continue
        mark = "*" if index == default_out else " "
        hostapi = sd.query_hostapis(info["hostapi"])["name"]
        lines.append(f"{mark} {index:3d}  {info['name']}  ({hostapi})")
    return "\n".join(lines)


def resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or samples.size == 0:
        return samples
    duration = samples.size / src_rate
    dst_size = max(1, round(duration * dst_rate))
    src_t = np.arange(samples.size) / src_rate
    dst_t = np.arange(dst_size) / dst_rate
    return np.interp(dst_t, src_t, samples).astype(np.float32)


def prepare(pcm: bytes, *, volume: float, normalize: bool, rate: int) -> np.ndarray:
    """Convert 16 kHz int16 PCM into float32 samples ready for the sound card."""
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if samples.size == 0:
        return samples
    if normalize:
        peak = float(np.max(np.abs(samples)))
        if peak > 0:
            samples = samples * min(NORMALIZE_PEAK / peak, NORMALIZE_MAX_GAIN)
    samples = samples * volume
    fade = min(samples.size // 2, int(FADE_SECONDS * SAMPLE_RATE))
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        samples[:fade] *= ramp
        samples[-fade:] *= ramp[::-1]
    samples = np.clip(samples, -1.0, 1.0).astype(np.float32)
    return resample(samples, SAMPLE_RATE, rate)


class Player:
    def __init__(
        self, device: str | int | None = None, volume: float = 1.0, normalize: bool = True
    ) -> None:
        sd = _import_sounddevice()
        self._sd = sd
        if isinstance(device, str) and device.strip().isdigit():
            device = int(device)
        try:
            info = sd.query_devices(device, "output")
        except (ValueError, sd.PortAudioError) as err:
            raise PlayerError(f"找不到輸出裝置 {device!r}：{err}") from err
        self._device = device
        self.device_name: str = info["name"]
        self.volume = volume
        self.normalize = normalize
        # Most sound cards accept 16 kHz directly; otherwise resample ourselves.
        try:
            sd.check_output_settings(device, channels=1, dtype="float32", samplerate=SAMPLE_RATE)
            self.samplerate = SAMPLE_RATE
        except sd.PortAudioError:
            self.samplerate = int(info["default_samplerate"])

    def describe(self) -> str:
        return f"{self.device_name}（{self.samplerate} Hz）"

    async def play(self, pcm: bytes) -> None:
        data = prepare(pcm, volume=self.volume, normalize=self.normalize, rate=self.samplerate)
        if data.size == 0:
            return
        loop = asyncio.get_running_loop()
        started = loop.time()
        self._sd.play(data, self.samplerate, device=self._device)
        try:
            stream = self._sd.get_stream()
            while stream.active:
                await asyncio.sleep(0.02)
            # Return only once the sound has really left the speaker: some
            # devices finish the stream early, and the output latency
            # (Bluetooth speakers!) delays the actual sound.
            ends = started + data.size / self.samplerate + float(stream.latency)
            await asyncio.sleep(max(0.0, ends - loop.time()))
        finally:
            self._sd.stop()
