from voice_pe_echo.segmenter import EventType, Segmenter, SegmenterConfig, State
from voice_pe_echo.vad import FRAME_BYTES, FRAME_SECONDS


def frames(seconds: float) -> int:
    return round(seconds / FRAME_SECONDS)


def feed(segmenter: Segmenter, pattern: list[tuple[float, float]]):
    """Feed (seconds, probability) runs; return the events with the frame index."""
    events = []
    index = 0
    for seconds, probability in pattern:
        for _ in range(frames(seconds)):
            frame = index.to_bytes(4, "little") * (FRAME_BYTES // 4)
            event = segmenter.process(frame, probability)
            if event is not None:
                events.append((index, event))
            index += 1
    return events


def test_one_sentence() -> None:
    seg = Segmenter()
    seg.reset(arm=False)
    events = feed(seg, [(1.0, 0.0), (1.5, 0.9), (1.5, 0.0)])
    assert [e.type for _, e in events] == [EventType.SPEECH_START, EventType.UTTERANCE]
    utterance = events[1][1].utterance
    # speech + pre-roll + kept tail, but not the whole trailing silence
    assert 1.6 < utterance.duration_s < 2.4
    assert abs(utterance.speech_s - 1.5) < 0.1
    # the first syllable is kept: the audio starts before the first speech frame
    first_frame_index = int.from_bytes(utterance.pcm[:4], "little")
    assert first_frame_index < frames(1.0)


def test_short_pause_does_not_split_sentence() -> None:
    seg = Segmenter()
    seg.reset(arm=False)
    events = feed(seg, [(0.5, 0.0), (1.0, 0.9), (0.4, 0.1), (1.0, 0.9), (1.2, 0.0)])
    assert [e.type for _, e in events] == [EventType.SPEECH_START, EventType.UTTERANCE]


def test_long_pause_splits_sentences() -> None:
    seg = Segmenter()
    seg.reset(arm=False)
    events = feed(seg, [(0.5, 0.0), (1.0, 0.9), (1.2, 0.0), (1.0, 0.9), (1.2, 0.0)])
    assert [e.type for _, e in events].count(EventType.UTTERANCE) == 2


def test_cough_is_discarded() -> None:
    seg = Segmenter()
    seg.reset(arm=False)
    events = feed(seg, [(0.5, 0.0), (0.22, 0.9), (1.2, 0.0)])
    assert [e.type for _, e in events] == [EventType.SPEECH_START, EventType.DISCARDED]


def test_blips_do_not_start_a_sentence() -> None:
    seg = Segmenter()
    seg.reset(arm=False)
    pattern = [(0.064, 0.9), (0.16, 0.0)] * 10
    assert feed(seg, pattern) == []


def test_max_length_cuts_endless_speech() -> None:
    seg = Segmenter(SegmenterConfig(max_utterance_s=5.0))
    seg.reset(arm=False)
    events = feed(seg, [(12.0, 0.9)])
    utterances = [e for _, e in events if e.type is EventType.UTTERANCE]
    assert len(utterances) == 2
    assert all(abs(u.utterance.duration_s - 5.0) < 0.1 for u in utterances)


def test_arming_ignores_speech_that_is_already_going_on() -> None:
    """After playback the gate re-opens in ARMING: an echo tail must not start a sentence."""
    seg = Segmenter()
    seg.reset(arm=True)
    events = feed(seg, [(0.5, 0.9)])
    assert events == []
    assert seg.state is State.ARMING
    events = feed(seg, [(0.3, 0.0), (1.0, 0.9), (1.0, 0.0)])
    assert [e.type for _, e in events] == [EventType.SPEECH_START, EventType.UTTERANCE]
