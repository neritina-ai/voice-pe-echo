"""Cut a continuous audio stream into sentences ("utterances").

The segmenter is fed 32 ms frames together with the VAD's speech probability
and reports when a sentence starts and when it is complete. It is pure logic
(no I/O, no clock) so it can be tested with synthetic input.

States:

* ARMING - after a reset, wait for a short stretch of silence before a new
  sentence may start. This keeps the tail of our own playback (which may still
  be in flight from the device when the feedback gate opens) from being
  mistaken for a new sentence.
* IDLE   - waiting for speech; the last few frames are kept as pre-roll so the
  first syllable is not cut off.
* SPEECH - recording until there has been enough silence (sentence complete),
  or the maximum length is reached.
"""

from __future__ import annotations

import enum
from collections import deque
from dataclasses import dataclass

from .vad import FRAME_SECONDS, SAMPLE_RATE


@dataclass
class SegmenterConfig:
    threshold: float = 0.5  # speech probability that counts as speech
    start_window_s: float = 0.32  # look at this much recent audio ...
    start_speech_s: float = 0.19  # ... and start once this much of it is speech
    end_silence_s: float = 0.8  # this much silence ends a sentence
    pre_roll_s: float = 0.3  # audio kept from before the detected start
    tail_s: float = 0.25  # silence kept after the last word
    min_speech_s: float = 0.3  # shorter sentences (coughs, clicks) are ignored
    max_utterance_s: float = 20.0  # longer sentences are cut here
    arm_silence_s: float = 0.25  # silence required after a reset


def _frames(seconds: float) -> int:
    return max(1, round(seconds / FRAME_SECONDS))


class State(enum.Enum):
    ARMING = "arming"
    IDLE = "idle"
    SPEECH = "speech"


class EventType(enum.Enum):
    SPEECH_START = "speech_start"
    UTTERANCE = "utterance"
    DISCARDED = "discarded"


@dataclass
class Utterance:
    pcm: bytes
    speech_s: float

    @property
    def duration_s(self) -> float:
        return len(self.pcm) / 2 / SAMPLE_RATE


@dataclass
class SegmentEvent:
    type: EventType
    utterance: Utterance | None = None


class Segmenter:
    def __init__(self, config: SegmenterConfig | None = None) -> None:
        self.config = config or SegmenterConfig()
        c = self.config
        self._start_window = _frames(c.start_window_s)
        self._start_speech = min(self._start_window, _frames(c.start_speech_s))
        self._end_silence = _frames(c.end_silence_s)
        self._tail = min(self._end_silence, _frames(c.tail_s))
        self._min_speech = _frames(c.min_speech_s)
        self._max_frames = _frames(c.max_utterance_s)
        self._arm_silence = _frames(c.arm_silence_s)
        # Silero recommends a lower threshold for "speech has stopped" than for
        # "speech has started" so a sentence is not cut on a soft syllable.
        self._silence_threshold = max(0.0, c.threshold - 0.15)
        self._pre_roll: deque[bytes] = deque(maxlen=self._start_window + _frames(c.pre_roll_s))
        self._window: deque[bool] = deque(maxlen=self._start_window)
        self._frames: list[bytes] = []
        self.reset()

    @property
    def state(self) -> State:
        return self._state

    def reset(self, arm: bool = True) -> None:
        """Forget everything; with arm=True require silence before the next start."""
        self._state = State.ARMING if arm else State.IDLE
        self._pre_roll.clear()
        self._window.clear()
        self._frames = []
        self._quiet_run = 0
        self._speech_frames = 0
        self._silence_run = 0

    def process(self, frame: bytes, probability: float) -> SegmentEvent | None:
        is_speech = probability >= self.config.threshold

        if self._state is State.ARMING:
            self._quiet_run = 0 if is_speech else self._quiet_run + 1
            self._pre_roll.append(frame)
            if self._quiet_run >= self._arm_silence:
                self._state = State.IDLE
            return None

        if self._state is State.IDLE:
            self._pre_roll.append(frame)
            self._window.append(is_speech)
            if sum(self._window) >= self._start_speech:
                self._state = State.SPEECH
                self._frames = list(self._pre_roll)
                self._speech_frames = sum(self._window)
                self._silence_run = 0
                self._pre_roll.clear()
                self._window.clear()
                return SegmentEvent(EventType.SPEECH_START)
            return None

        self._frames.append(frame)
        if is_speech:
            self._speech_frames += 1
        if probability >= self._silence_threshold:
            self._silence_run = 0
        else:
            self._silence_run += 1

        if self._silence_run >= self._end_silence:
            keep = len(self._frames) - self._silence_run + self._tail
            return self._finish(self._frames[:keep])
        if len(self._frames) >= self._max_frames:
            return self._finish(self._frames)
        return None

    def _finish(self, frames: list[bytes]) -> SegmentEvent:
        speech_frames = self._speech_frames
        self._state = State.IDLE
        self._frames = []
        self._speech_frames = 0
        self._silence_run = 0
        if speech_frames < self._min_speech:
            return SegmentEvent(EventType.DISCARDED)
        return SegmentEvent(
            EventType.UTTERANCE,
            Utterance(pcm=b"".join(frames), speech_s=speech_frames * FRAME_SECONDS),
        )
