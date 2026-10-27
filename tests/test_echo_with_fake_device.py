"""End-to-end tests: the real program against a fake Voice PE (tests/fake_voice_pe.py)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

import pytest
from aioesphomeapi import APIClient

from fake_voice_pe import FakeVoicePE, Room, speech_like
from voice_pe_echo import device as device_module
from voice_pe_echo.app import EchoApp
from voice_pe_echo.device import VoicePE
from voice_pe_echo.segmenter import Segmenter
from voice_pe_echo.vad import EnergyVad

RUN_END, STT_START, STT_VAD_START = 2, 3, 11


@pytest.fixture(autouse=True)
def fast_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device_module, "SUBSCRIBE_SETTLE_S", 0.2)
    monkeypatch.setattr(device_module, "RESTART_DELAY_S", 0.3)
    monkeypatch.setattr(device_module, "OCCUPIED_RETRY_S", 0.8)
    monkeypatch.setattr(device_module, "START_TIMEOUT_S", 2.0)
    monkeypatch.setattr(device_module, "RECONNECT_MIN_S", 0.3)


class EchoingPlayer:
    """Plays nothing, but lets the fake room hear the playback like a real speaker would."""

    def __init__(self, room: Room, delay_s: float = 0.15, gain: float = 0.6) -> None:
        self.room = room
        self.delay_s = delay_s
        self.gain = gain
        self.played: list[bytes] = []

    async def play(self, pcm: bytes) -> None:
        self.played.append(pcm)
        self.room.add_pcm_now(pcm, self.delay_s, self.gain)
        await asyncio.sleep(len(pcm) / 2 / 16000)


class UngatedEchoApp(EchoApp):
    """Control group: the same app with the feedback gate removed."""

    def _process_frame(self, frame: bytes) -> None:
        self._playing = False
        self._gate_until = 0.0
        self._gate_dirty = False
        super()._process_frame(frame)


async def wait_until(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


@contextlib.asynccontextmanager
async def running(fake: FakeVoicePE, player, app_class=EchoApp):
    await fake.start()
    app = app_class(vad=EnergyVad(), segmenter=Segmenter(), player=player, guard_s=0.6)
    voice = VoicePE("127.0.0.1", app, port=fake.port)
    app.device = voice
    task = asyncio.create_task(voice.run())
    try:
        yield app, voice
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await app.close()
        await asyncio.sleep(0.1)
        await fake.stop()


def two_sentences_room() -> Room:
    room = Room()
    room.add(speech_like(1.2, seed=1), at_s=1.0)
    room.add(speech_like(1.0, seed=2), at_s=7.0)
    return room


def test_echoes_each_sentence_once_without_feedback() -> None:
    async def scenario() -> None:
        room = two_sentences_room()
        fake = FakeVoicePE(room)
        player = EchoingPlayer(room)
        async with running(fake, player) as (_app, voice):
            assert await wait_until(lambda: fake.streaming, 3.0), "stream never started"
            assert fake.announcements[0].start_conversation
            await wait_until(lambda: room.position / 16000 > 12.0, 15.0)
            assert voice.streaming
        assert len(player.played) == 2
        for pcm in player.played:
            assert 1.0 < len(pcm) / 32000 < 2.6
        assert fake.events.count(STT_VAD_START) == 2
        assert STT_START in fake.events
        assert fake.events[-1] == RUN_END  # microphone closed on exit
        assert fake.va_holder is None

    asyncio.run(scenario())


def test_without_gate_the_scenario_really_feeds_back() -> None:
    async def scenario() -> None:
        room = two_sentences_room()
        fake = FakeVoicePE(room)
        player = EchoingPlayer(room)
        async with running(fake, player, UngatedEchoApp):
            assert await wait_until(lambda: fake.streaming, 3.0)
            await wait_until(lambda: room.position / 16000 > 12.0, 15.0)
        assert len(player.played) > 2

    asyncio.run(scenario())


@pytest.mark.parametrize("split_logs", [False, True], ids=["new-firmware-log", "old-firmware-log"])
def test_waits_while_home_assistant_holds_the_voice_assistant(caplog, split_logs: bool) -> None:
    caplog.set_level(logging.INFO)

    async def scenario() -> None:
        fake = FakeVoicePE(split_logs=split_logs)
        fake.va_holder = "Home Assistant 2026.10.1 (192.168.1.10)"
        async with running(fake, EchoingPlayer(fake.room)):
            await asyncio.sleep(1.0)
            assert not fake.streaming
            assert not fake.announcements  # no point starting a run for someone else
            assert "Home Assistant 2026.10.1 (192.168.1.10)" in caplog.text
            fake.va_holder = None  # the user disabled the device in Home Assistant
            assert await wait_until(lambda: fake.streaming, 4.0)

    asyncio.run(scenario())


def test_home_assistant_connecting_later_does_not_interrupt(caplog) -> None:
    caplog.set_level(logging.INFO)

    async def scenario() -> None:
        fake = FakeVoicePE()
        async with running(fake, EchoingPlayer(fake.room)) as (_app, voice):
            assert await wait_until(lambda: fake.streaming, 3.0)
            hass = APIClient("127.0.0.1", fake.port, None, client_info="Home Assistant 2026.10.1")
            await hass.connect(login=True)

            async def no_op(*_args):
                return None

            hass.subscribe_voice_assistant(handle_start=no_op, handle_stop=no_op)
            await asyncio.sleep(1.0)
            assert "也想使用 Voice PE 的語音助理" in caplog.text
            assert voice.streaming and fake.streaming and fake.pipeline_starts == 1
            await hass.disconnect()

    asyncio.run(scenario())


def test_restarts_after_button_press() -> None:
    async def scenario() -> None:
        fake = FakeVoicePE()
        async with running(fake, EchoingPlayer(fake.room)) as (_app, voice):
            assert await wait_until(lambda: fake.streaming, 3.0)
            fake.press_button()
            assert await wait_until(lambda: not voice.streaming, 1.0)
            assert await wait_until(lambda: fake.streaming and voice.streaming, 3.0)
            assert fake.pipeline_starts == 2

    asyncio.run(scenario())


def test_mute_switch_pauses_listening() -> None:
    async def scenario() -> None:
        fake = FakeVoicePE()
        async with running(fake, EchoingPlayer(fake.room)) as (_app, voice):
            assert await wait_until(lambda: fake.streaming, 3.0)
            fake.set_muted(True)
            assert await wait_until(lambda: not fake.streaming and not voice.streaming, 1.0)
            assert RUN_END in fake.events
            announcements = len(fake.announcements)
            await asyncio.sleep(1.0)
            assert len(fake.announcements) == announcements  # stays quiet while muted
            fake.set_muted(False)
            assert await wait_until(lambda: fake.streaming and voice.streaming, 3.0)

    asyncio.run(scenario())


def test_reconnects_after_connection_loss() -> None:
    async def scenario() -> None:
        fake = FakeVoicePE()
        async with running(fake, EchoingPlayer(fake.room)) as (_app, voice):
            assert await wait_until(lambda: fake.streaming, 3.0)
            for conn in list(fake.connections):
                conn.writer.close()  # e.g. Wi-Fi dropped
            assert await wait_until(lambda: not voice.connected, 2.0)
            assert await wait_until(lambda: fake.streaming and voice.streaming, 5.0)

    asyncio.run(scenario())
