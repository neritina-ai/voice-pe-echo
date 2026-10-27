"""The echo itself: audio in -> sentence detection -> playback, without feedback.

Feedback ("回授") would happen because the PC speaker's sound reaches the
Voice PE microphone, gets detected as a new sentence and played again, forever.
The Voice PE's echo canceller cannot help: it only knows what the Voice PE
itself plays, not what the PC plays. So the echo works half-duplex, like a
walkie-talkie:

1. While a sentence is being played, incoming audio is ignored.
2. After playback ends, audio is ignored for another ``guard_s`` seconds
   (room reverberation, sound-card buffers and network delay).
3. After that the segmenter is reset into its ARMING state, so a sentence can
   only start after a moment of silence; a late echo tail cannot start one.
"""

from __future__ import annotations

import asyncio
import logging
import time
import wave
from pathlib import Path
from typing import Any, Protocol

from .segmenter import EventType, Segmenter, State, Utterance
from .vad import FRAME_BYTES, SAMPLE_RATE, Vad, frame_dbfs

_LOGGER = logging.getLogger(__name__)


class PlayerLike(Protocol):
    async def play(self, pcm: bytes) -> None: ...


class EchoApp:
    def __init__(
        self,
        *,
        vad: Vad,
        segmenter: Segmenter,
        player: PlayerLike,
        guard_s: float = 0.6,
        save_dir: Path | None = None,
    ) -> None:
        self.device: Any = None  # VoicePE, for LED feedback; set after construction
        self._vad = vad
        self._segmenter = segmenter
        self._player = player
        self._guard_s = guard_s
        self._save_dir = save_dir
        self._buffer = bytearray()
        self._playing = False
        self._gate_until = 0.0
        self._gate_dirty = False
        self._playback: asyncio.Task[None] | None = None
        self._said_hello = False
        self.level_db = -100.0
        self.level_time = 0.0
        self.sentences = 0

    # ------------------------------------------------------ device listener

    def on_stream_start(self) -> None:
        self._buffer.clear()
        self._vad.reset()
        self._segmenter.reset(arm=False)
        if not self._said_hello:
            _LOGGER.info("開始收音：對著 Voice PE 說一句話，電腦就會原音重播（按 Ctrl+C 結束）")
            self._said_hello = True
        else:
            _LOGGER.info("恢復收音")

    def on_stream_stop(self) -> None:
        self._buffer.clear()
        self._segmenter.reset()

    def on_audio(self, pcm: bytes) -> None:
        self._buffer += pcm
        while len(self._buffer) >= FRAME_BYTES:
            frame = bytes(self._buffer[:FRAME_BYTES])
            del self._buffer[:FRAME_BYTES]
            self._process_frame(frame)

    # ------------------------------------------------------------ pipeline

    def _process_frame(self, frame: bytes) -> None:
        now = time.monotonic()
        self.level_db = frame_dbfs(frame)
        self.level_time = now
        if self._playing or now < self._gate_until:
            self._gate_dirty = True
            return
        if self._gate_dirty:
            self._gate_dirty = False
            self._vad.reset()
            self._segmenter.reset(arm=True)

        event = self._segmenter.process(frame, self._vad(frame))
        if event is None:
            return
        if event.type is EventType.SPEECH_START:
            _LOGGER.info("偵測到說話，錄音中…")
            self._device_call("indicate_speech")
        elif event.type is EventType.DISCARDED:
            _LOGGER.info("聲音太短，不像一句話，略過")
            self._device_call("indicate_listening")
        else:
            assert event.utterance is not None
            self._device_call("indicate_listening")
            self._start_playback(event.utterance)

    def _start_playback(self, utterance: Utterance) -> None:
        self.sentences += 1
        _LOGGER.info(
            "第 %d 句：%.1f 秒，從電腦喇叭播放…", self.sentences, utterance.duration_s
        )
        self._playing = True
        self._playback = asyncio.get_running_loop().create_task(self._play(utterance))

    async def _play(self, utterance: Utterance) -> None:
        try:
            if self._save_dir is not None:
                self._save(utterance)
            await self._player.play(utterance.pcm)
        except Exception as err:  # keep listening even if the sound card hiccups
            _LOGGER.error("播放失敗：%s", err)
        finally:
            self._playing = False
            self._gate_until = time.monotonic() + self._guard_s
            self._gate_dirty = True
        _LOGGER.info("播放完畢，繼續收音")

    def _save(self, utterance: Utterance) -> None:
        assert self._save_dir is not None
        self._save_dir.mkdir(parents=True, exist_ok=True)
        path = self._save_dir / time.strftime(f"%Y%m%d-%H%M%S-{self.sentences:04d}.wav")
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(utterance.pcm)
        _LOGGER.info("已存檔：%s", path)

    def _device_call(self, method: str) -> None:
        if self.device is not None:
            getattr(self.device, method)()

    async def close(self) -> None:
        if self._playback is not None and not self._playback.done():
            self._playback.cancel()
            try:
                await self._playback
            except asyncio.CancelledError:
                pass

    # -------------------------------------------------------------- status

    def status_text(self) -> str:
        device = self.device
        if device is not None and not device.connected:
            return "未連線"
        if device is not None and device.muted:
            return "Voice PE 靜音中"
        if device is not None and not device.streaming:
            return "等待開始收音"
        if self._playing:
            return "播放中"
        if time.monotonic() < self._gate_until:
            return "防回授等待"
        if self._segmenter.state is State.SPEECH:
            return "錄音中"
        return "收音中"
