"""A fake Voice PE speaking the ESPHome native API (plaintext), for tests.

It mimics the parts of the real firmware's voice_assistant component that
voice-pe-echo relies on (esphome/components/voice_assistant/voice_assistant.cpp):

* only one client may subscribe to the voice assistant; a second one is
  rejected with the "Multiple API Clients ..." error log;
* an announcement with start_conversation=True is followed by
  VoiceAssistantAnnounceFinished and then a pipeline start request;
* after VoiceAssistantResponse(port=0) the microphone streams 32 ms chunks
  over the API until RUN_END / STT_VAD_END arrives or the run is stopped;
* pressing the button while streaming stops the run (VoiceAssistantRequest start=False).

The microphone hears a simulated room (see Room), so tests can inject the
PC's playback back into the microphone and check that no feedback loop forms.
"""

from __future__ import annotations

import asyncio
import contextlib

import numpy as np
from aioesphomeapi import api_pb2 as pb
from aioesphomeapi.core import MESSAGE_TYPE_TO_PROTO

PROTO_TO_TYPE = {cls: num for num, cls in MESSAGE_TYPE_TO_PROTO.items()}
RATE = 16000
CHUNK = 512
MUTE_KEY = 1
FEATURES = 1 | 4 | 16 | 32 | 64  # voice assistant, API audio, announce, start conversation, multi channel


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


async def _read_varint(reader: asyncio.StreamReader) -> int:
    result = shift = 0
    while True:
        byte = (await reader.readexactly(1))[0]
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result
        shift += 7


def speech_like(seconds: float, level: float = 0.15, seed: int = 0) -> np.ndarray:
    """Voiced-sounding test signal: harmonics with a 4 Hz syllable envelope."""
    t = np.arange(int(seconds * RATE)) / RATE
    rng = np.random.default_rng(seed)
    tone = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) / (i + 1) for i, f in enumerate((180, 360, 540, 720)))
    envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 4 * t)
    return (level * tone * envelope / 1.5).astype(np.float32)


class Room:
    """Everything the microphone hears, on a clock that runs while streaming."""

    def __init__(self, seconds: float = 120.0, noise: float = 0.001) -> None:
        rng = np.random.default_rng(1)
        self.audio = (rng.standard_normal(int(seconds * RATE)) * noise).astype(np.float32)
        self.position = 0  # samples already sent

    def add(self, signal: np.ndarray, at_s: float) -> None:
        start = int(at_s * RATE)
        self.audio[start : start + signal.size] += signal[: self.audio.size - start]

    def add_pcm_now(self, pcm: bytes, delay_s: float, gain: float, reverb_s: float = 0.3) -> None:
        """Mix PC playback into the room (as heard by the mic), with a decaying tail."""
        signal = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0 * gain
        tail = int(reverb_s * RATE)
        if tail and signal.size:
            decay = np.exp(-np.arange(tail) / (tail / 4)).astype(np.float32)
            signal = np.concatenate([signal, signal[-tail:][::-1] * decay * 0.5])
        self.add(signal, self.position / RATE + delay_s)

    def read(self) -> bytes:
        chunk = self.audio[self.position : self.position + CHUNK]
        self.position += CHUNK
        return (np.clip(chunk, -1, 1) * 32767).astype("<i2").tobytes()


class _Conn:
    def __init__(self, device: FakeVoicePE, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.device = device
        self.reader = reader
        self.writer = writer
        self.log_level = 0
        self.states = False
        self.name = "?"

    def send(self, msg) -> None:
        data = msg.SerializeToString()
        self.writer.write(b"\0" + _varint(len(data)) + _varint(PROTO_TO_TYPE[type(msg)]) + data)

    async def serve(self) -> None:
        try:
            while True:
                if (await self.reader.readexactly(1)) != b"\0":
                    return  # not plaintext (e.g. a Noise client): hang up
                length = await _read_varint(self.reader)
                msg_type = await _read_varint(self.reader)
                data = await self.reader.readexactly(length)
                cls = MESSAGE_TYPE_TO_PROTO.get(msg_type)
                if cls is not None:
                    self.device.handle(self, cls.FromString(data))
                await self.writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self.device.connection_lost(self)
            self.writer.close()


class FakeVoicePE:
    def __init__(self, room: Room | None = None, split_logs: bool = False) -> None:
        self.room = room or Room()
        self.split_logs = split_logs  # old firmware logged the rejection over several lines
        self.connections: list[_Conn] = []
        self.va_holder: _Conn | str | None = None  # a str stands for Home Assistant
        self.events: list[int] = []
        self.announcements: list[pb.VoiceAssistantAnnounceRequest] = []
        self.pipeline_starts = 0
        self.streaming = False
        self.muted = False
        self._stream_task: asyncio.Task | None = None
        self._server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._accept, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self._stop_stream()
        for conn in list(self.connections):
            conn.writer.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        conn = _Conn(self, reader, writer)
        self.connections.append(conn)
        await conn.serve()

    def connection_lost(self, conn: _Conn) -> None:
        if conn in self.connections:
            self.connections.remove(conn)
        if self.va_holder is conn:
            self.va_holder = None
            self._stop_stream()

    # ------------------------------------------------------------ messages

    def handle(self, conn: _Conn, msg) -> None:  # noqa: C901
        if isinstance(msg, pb.HelloRequest):
            conn.name = msg.client_info
            conn.send(pb.HelloResponse(api_version_major=1, api_version_minor=13, server_info="fake", name="home-assistant-voice-fake"))
        elif isinstance(msg, pb.PingRequest):
            conn.send(pb.PingResponse())
        elif isinstance(msg, pb.DisconnectRequest):
            conn.send(pb.DisconnectResponse())
            conn.writer.close()
        elif isinstance(msg, pb.DeviceInfoRequest):
            conn.send(
                pb.DeviceInfoResponse(
                    name="home-assistant-voice-fake",
                    friendly_name="Fake Voice PE",
                    esphome_version="2026.9.0",
                    project_name="Nabu Casa.Home Assistant Voice PE",
                    project_version="26.9.0",
                    mac_address="AA:BB:CC:DD:EE:FF",
                    voice_assistant_feature_flags=FEATURES,
                )
            )
        elif isinstance(msg, pb.ListEntitiesRequest):
            conn.send(pb.ListEntitiesSwitchResponse(object_id="mute", key=MUTE_KEY, name="Mute"))
            conn.send(pb.ListEntitiesDoneResponse())
        elif isinstance(msg, pb.SubscribeStatesRequest):
            conn.states = True
            conn.send(pb.SwitchStateResponse(key=MUTE_KEY, state=self.muted))
        elif isinstance(msg, pb.SubscribeLogsRequest):
            conn.log_level = msg.level
        elif isinstance(msg, pb.SubscribeVoiceAssistantRequest):
            self._subscribe(conn, msg.subscribe)
        elif isinstance(msg, pb.VoiceAssistantAnnounceRequest):
            self.announcements.append(msg)
            asyncio.get_running_loop().call_later(0.2, self._announce_done, conn, msg.start_conversation)
        elif isinstance(msg, pb.VoiceAssistantResponse):
            if conn is self.va_holder and not msg.error:
                self._start_stream(conn)
        elif isinstance(msg, pb.VoiceAssistantEventResponse):
            self.events.append(msg.event_type)
            if msg.event_type in (2, 12):  # RUN_END, STT_VAD_END
                self._stop_stream()

    def _log(self, level: int, text: str) -> None:
        for conn in self.connections:
            if conn.log_level >= level:
                conn.send(pb.SubscribeLogsResponse(level=level, message=f"\x1b[1;31m[E][voice_assistant]: {text}\x1b[0m".encode()))

    def _subscribe(self, conn: _Conn, subscribe: bool) -> None:
        if not subscribe:
            if self.va_holder is conn:
                self.va_holder = None
                self._stop_stream()
            else:
                self._log(1, "Client attempting to unsubscribe that is not the current API Client")
            return
        if self.va_holder is not None:
            current = self.va_holder if isinstance(self.va_holder, str) else f"{self.va_holder.name} (127.0.0.1)"
            lines = [
                "Multiple API Clients attempting to connect to Voice Assistant",
                f"  Current client: {current}",
                f"  New client: {conn.name} (127.0.0.1)",
            ]
            for text in lines if self.split_logs else ["\n".join(lines)]:
                self._log(1, text)
            return
        self.va_holder = conn

    def _announce_done(self, conn: _Conn, start_conversation: bool) -> None:
        if conn not in self.connections:
            return
        conn.send(pb.VoiceAssistantAnnounceFinished(success=True))
        if start_conversation:
            self._request_start()

    def _request_start(self) -> None:
        if isinstance(self.va_holder, _Conn) and not self.streaming:
            self.pipeline_starts += 1
            self.va_holder.send(pb.VoiceAssistantRequest(start=True, conversation_id="", flags=0))

    # ------------------------------------------------------------ streaming

    def _start_stream(self, conn: _Conn) -> None:
        self._stop_stream()
        self.streaming = True
        self._stream_task = asyncio.get_running_loop().create_task(self._stream(conn))

    def _stop_stream(self) -> None:
        self.streaming = False
        if self._stream_task is not None:
            self._stream_task.cancel()
            self._stream_task = None

    async def _stream(self, conn: _Conn) -> None:
        loop = asyncio.get_running_loop()
        start = loop.time()
        sent = 0
        with contextlib.suppress(ConnectionError):
            while True:
                chunk = self.room.read()
                conn.send(pb.VoiceAssistantAudio(data=chunk, data2=chunk))
                sent += 1
                await asyncio.sleep(max(0.0, start + sent * CHUNK / RATE - loop.time()))

    # --------------------------------------------------- physical controls

    def press_button(self) -> None:
        """Center button: stop a running pipeline, otherwise start one."""
        if self.streaming:
            self._stop_stream()
            if isinstance(self.va_holder, _Conn):
                self.va_holder.send(pb.VoiceAssistantRequest(start=False))
        else:
            self._request_start()

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        for conn in self.connections:
            if conn.states:
                conn.send(pb.SwitchStateResponse(key=MUTE_KEY, state=muted))


async def _serve_forever(port: int) -> None:
    room = Room(seconds=600)
    for i, at in enumerate(range(2, 590, 6)):
        room.add(speech_like(1.0 + (i % 3) * 0.4, seed=i), at_s=at)
    device = FakeVoicePE(room)
    device._server = await asyncio.start_server(device._accept, "127.0.0.1", port)
    print(f"Fake Voice PE listening on 127.0.0.1:{port} (a 'sentence' every 6 s)")
    await asyncio.Event().wait()


if __name__ == "__main__":
    import sys

    asyncio.run(_serve_forever(int(sys.argv[1]) if len(sys.argv) > 1 else 6053))
