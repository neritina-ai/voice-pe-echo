import numpy as np

from voice_pe_echo.player import NORMALIZE_MAX_GAIN, prepare, resample
from voice_pe_echo.vad import EnergyVad, frame_dbfs


def pcm(samples: np.ndarray) -> bytes:
    return (samples * 32767).astype("<i2").tobytes()


def tone(seconds: float, level: float, rate: int = 16000) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (level * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def test_frame_dbfs() -> None:
    assert frame_dbfs(bytes(1024)) == -100.0
    assert abs(frame_dbfs(pcm(tone(0.032, 1.0))) - (-3.0)) < 0.2


def test_prepare_normalizes_and_fades() -> None:
    out = prepare(pcm(tone(1.0, 0.3)), volume=1.0, normalize=True, rate=16000)
    assert abs(float(np.max(np.abs(out))) - 0.89) < 0.01
    assert abs(out[0]) < 1e-3 and abs(out[-1]) < 1e-3


def test_prepare_does_not_blow_up_near_silence() -> None:
    out = prepare(pcm(tone(1.0, 0.001)), volume=1.0, normalize=True, rate=16000)
    assert float(np.max(np.abs(out))) <= 0.001 * NORMALIZE_MAX_GAIN * 1.01


def test_resample_keeps_duration() -> None:
    out = resample(tone(1.0, 0.5), 16000, 48000)
    assert out.size == 48000
    assert out.dtype == np.float32


def test_energy_vad_learns_noise_floor() -> None:
    vad = EnergyVad()
    rng = np.random.default_rng(0)
    noise = [pcm((rng.standard_normal(512) * 0.003).astype(np.float32)) for _ in range(50)]
    assert sum(vad(frame) for frame in noise) == 0
    speech = pcm(tone(0.032, 0.2))
    assert vad(speech) == 1.0
