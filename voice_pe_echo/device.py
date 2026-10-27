"""Talk to the Voice PE over the ESPHome native API.

Normally Home Assistant is the Voice PE's "voice assistant server": after the
wake word the device streams its microphone to Home Assistant, which runs
speech-to-text and tells the device when the sentence is over. This module
plays that server role instead, with two twists:

* It starts the stream itself, without a wake word: it sends an announcement
  with ``start_conversation=True`` (the same mechanism Home Assistant's
  ``assist_satellite.start_conversation`` uses). The device plays its wake
  sound and then opens the microphone.
* It never tells the device that the sentence is over, so the microphone stays
  open and the device keeps streaming audio until we stop it. Sentence
  boundaries are detected on the PC instead.

A Voice PE accepts only one voice assistant client at a time, so Home
Assistant must not be connected to it while this program runs.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from typing import Any, Protocol

from aioesphomeapi import (
    APIClient,
    APIConnectionError,
    InvalidEncryptionKeyAPIError,
    LogLevel,
    RequiresEncryptionAPIError,
    SwitchInfo,
    SwitchState,
    VoiceAssistantEventType,
    VoiceAssistantFeature,
)
from aioesphomeapi.core import EncryptionPlaintextAPIError

from . import __version__

DEFAULT_PORT = 6053
# A sound stored in the Voice PE firmware (26.x and later). Older firmware
# cannot play it, but still starts listening ~2 s later (playback timeout).
DEFAULT_START_SOUND = "audio-file://wake_word_triggered_sound"

RECONNECT_MIN_S = 2.0
RECONNECT_MAX_S = 30.0
SUBSCRIBE_SETTLE_S = 1.0  # time for the device to report a rejected subscription
START_TIMEOUT_S = 15.0  # how long a start request may take before we complain
RESTART_DELAY_S = 1.5  # pause before restarting a stream the device stopped
OCCUPIED_RETRY_S = 30.0
ANNOUNCE_TIMEOUT_S = 30.0

CLIENT_NAME = "voice-pe-echo"  # how the device names us in its logs
OCCUPIED_MARKER = "Multiple API Clients attempting to connect to Voice Assistant"
_CURRENT_CLIENT_RE = re.compile(r"Current client:\s*(.+)")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_LOGGER = logging.getLogger(__name__)


class Listener(Protocol):
    def on_stream_start(self) -> None: ...

    def on_audio(self, pcm: bytes) -> None: ...

    def on_stream_stop(self) -> None: ...


class FatalDeviceError(Exception):
    """A problem that retrying cannot fix (wrong key, unsupported device...)."""


class VoicePE:
    def __init__(
        self,
        host: str,
        listener: Listener,
        *,
        port: int = DEFAULT_PORT,
        key: str | None = None,
        addresses: list[str] | None = None,
        start_sound: str = DEFAULT_START_SOUND,
        led_feedback: bool = True,
        device_logs: bool = False,
        zeroconf_instance: Any = None,
    ) -> None:
        self._host = host
        self._listener = listener
        self._port = port
        self._key = key or None
        self._addresses = addresses
        self._start_sound = start_sound
        self._led_feedback = led_feedback
        self._device_logs = device_logs
        self._zeroconf = zeroconf_instance

        self.name = host
        self.connected = False
        self.streaming = False
        self.muted: bool | None = None
        self._client: APIClient | None = None
        self._unsub_va: Callable[[], None] | None = None
        self._occupied_by: str | None = None
        self._rejection_seen = False
        self._can_kick = False
        self._mute_key: int | None = None
        self._changed = asyncio.Event()
        self._tasks: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------------ run

    async def run(self) -> None:
        """Stay connected (reconnecting as needed) until cancelled."""
        delay = RECONNECT_MIN_S
        while True:
            if await self._session():
                delay = RECONNECT_MIN_S
            else:
                # The IP address may have changed: resolve the name next time.
                self._addresses = None
            _LOGGER.info("%.0f 秒後重新連線…", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_S)

    async def _session(self) -> bool:
        """Connect once and serve until disconnected. Returns False if connecting failed."""
        client = APIClient(
            self._host,
            self._port,
            None,
            client_info=f"{CLIENT_NAME} {__version__}",
            noise_psk=self._key,
            addresses=self._addresses,
            zeroconf_instance=self._zeroconf,
        )
        disconnected = asyncio.Event()

        async def on_stop(expected_disconnect: bool) -> None:
            disconnected.set()

        _LOGGER.info("連線到 Voice PE（%s）…", self._host)
        try:
            await client.connect(on_stop=on_stop, login=True)
        except RequiresEncryptionAPIError as err:
            raise FatalDeviceError(
                "這台 Voice PE 設有 API 加密金鑰，請用 --key 或設定檔提供金鑰。"
                "取得方式請見 docs/user-guide.md「取得加密金鑰」。"
            ) from err
        except InvalidEncryptionKeyAPIError as err:
            raise FatalDeviceError(
                "加密金鑰不正確。請確認金鑰是這台 Voice PE 的；"
                "若裝置已恢復原廠設定（沒有金鑰），請不要提供 --key。"
            ) from err
        except EncryptionPlaintextAPIError as err:
            raise FatalDeviceError("這台裝置沒有啟用加密，請不要提供 --key。") from err
        except APIConnectionError as err:
            reason = str(err).rsplit(": ", 1)[-1]
            _LOGGER.warning(
                "無法連線到 Voice PE（%s）：%s。請確認它已通電、連上 Wi-Fi，且位址正確",
                self._host,
                reason,
            )
            return False

        self._client = client
        self.connected = True
        try:
            await self._serve(client, disconnected)
        except APIConnectionError as err:
            _LOGGER.warning("與 %s 的連線中斷：%s", self.name, err)
        finally:
            await self._teardown(client)
        return True

    async def _serve(self, client: APIClient, disconnected: asyncio.Event) -> None:
        info = await client.device_info()
        self.name = info.friendly_name or info.name
        _LOGGER.info(
            "已連線：%s（韌體 %s，ESPHome %s）",
            self.name,
            info.project_version or "未知",
            info.esphome_version,
        )
        if info.project_name and "voice" not in info.project_name.lower():
            _LOGGER.warning("這台裝置看起來不是 Voice PE（%s），仍然嘗試使用", info.project_name)

        assert client.api_version is not None
        flags = info.voice_assistant_feature_flags_compat(client.api_version)
        if not flags & VoiceAssistantFeature.VOICE_ASSISTANT:
            raise FatalDeviceError(f"{self.name} 沒有語音助理功能，無法收音。")
        if not flags & VoiceAssistantFeature.API_AUDIO:
            raise FatalDeviceError(
                f"{self.name} 的韌體太舊（不支援透過 API 傳送音訊），請先更新 Voice PE 韌體。"
            )
        self._can_kick = bool(flags & VoiceAssistantFeature.START_CONVERSATION)

        entities, _services = await client.list_entities_services()
        self._mute_key = next(
            (
                e.key
                for e in entities
                if isinstance(e, SwitchInfo) and "mute" in (e.object_id, e.name.lower())
            ),
            None,
        )
        client.subscribe_states(self._on_state)
        client.subscribe_logs(
            self._on_log,
            log_level=LogLevel.LOG_LEVEL_DEBUG if self._device_logs else LogLevel.LOG_LEVEL_WARN,
        )
        self._subscribe_voice_assistant(client)

        keeper = asyncio.create_task(self._keep_streaming(client))
        waiter = asyncio.create_task(disconnected.wait())
        try:
            done, _pending = await asyncio.wait(
                {keeper, waiter}, return_when=asyncio.FIRST_COMPLETED
            )
            if keeper in done:
                keeper.result()  # re-raise whatever stopped it
            _LOGGER.warning("與 %s 的連線中斷", self.name)
        finally:
            for task in (keeper, waiter):
                task.cancel()

    async def _teardown(self, client: APIClient) -> None:
        was_streaming = self.streaming
        self._set_streaming(False)
        for task in list(self._tasks):
            task.cancel()
        try:
            if was_streaming:
                self._end_run()  # close the microphone so the device goes back to normal
            if self._unsub_va is not None:
                self._unsub_va()
            await asyncio.wait_for(client.disconnect(), timeout=3)
        except (APIConnectionError, TimeoutError):
            pass
        finally:
            self._unsub_va = None
            self._client = None
            self.connected = False
            self.muted = None

    # ------------------------------------------------- keep the stream open

    async def _keep_streaming(self, client: APIClient) -> None:
        await asyncio.sleep(SUBSCRIBE_SETTLE_S)
        failures = 0
        told_muted = told_wake = False
        while True:
            if self._occupied_by is not None:
                _LOGGER.error(
                    "Voice PE 的語音助理正被另一個程式使用（%s）。"
                    "通常是 Home Assistant：請在 HA 停用這台裝置（見 docs/user-guide.md）。"
                    "%.0f 秒後再試…",
                    self._occupied_by,
                    OCCUPIED_RETRY_S,
                )
                await asyncio.sleep(OCCUPIED_RETRY_S)
                self._subscribe_voice_assistant(client)
                await asyncio.sleep(SUBSCRIBE_SETTLE_S)
                continue

            if self.streaming:
                await self._wait_for(lambda: not self.streaming)
                await asyncio.sleep(RESTART_DELAY_S)
                continue

            if self.muted:
                if not told_muted:
                    _LOGGER.warning("Voice PE 目前是靜音狀態：把側邊的靜音開關切回來就會自動開始收音")
                    told_muted = True
                await self._wait_for(lambda: not self.muted or self._occupied_by is not None)
                continue
            told_muted = False

            if not self._can_kick:
                if not told_wake:
                    _LOGGER.warning(
                        "這版韌體不支援自動開始收音：請說一次「Okay Nabu」或按一下中央按鈕，"
                        "之後就會持續收音。建議更新 Voice PE 韌體。"
                    )
                    told_wake = True
                await self._wait_for(lambda: self.streaming or self._occupied_by is not None)
                continue

            _LOGGER.info("請 Voice PE 開始收音…")
            self._kick(client)
            started = await self._wait_for(
                lambda: self.streaming or self._occupied_by is not None, START_TIMEOUT_S
            )
            if started:
                failures = 0
                continue
            failures += 1
            retry = min(30.0 * 2 ** (failures - 1), 300.0)
            _LOGGER.warning(
                "Voice PE 沒有開始傳送聲音（等了 %.0f 秒）。可能原因：Home Assistant 仍連著這台裝置，"
                "或裝置正在播放/忙碌。也可以說「Okay Nabu」或按一下中央按鈕手動開始。%.0f 秒後再試…",
                START_TIMEOUT_S,
                retry,
            )
            await self._wait_for(lambda: self.streaming or self._occupied_by is not None, retry)

    def _kick(self, client: APIClient) -> None:
        async def announce() -> None:
            try:
                await client.send_voice_assistant_announcement_await_response(
                    self._start_sound, ANNOUNCE_TIMEOUT_S, start_conversation=True
                )
            except APIConnectionError as err:
                _LOGGER.debug("Start announcement did not finish: %s", err)

        self._spawn(announce())

    async def _wait_for(self, predicate: Callable[[], bool], timeout: float | None = None) -> bool:
        try:
            async with asyncio.timeout(timeout):
                while not predicate():
                    self._changed.clear()
                    await self._changed.wait()
        except TimeoutError:
            pass
        return predicate()

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _set_streaming(self, streaming: bool) -> None:
        if streaming == self.streaming:
            return
        self.streaming = streaming
        self._changed.set()
        if streaming:
            self._listener.on_stream_start()
        else:
            self._listener.on_stream_stop()

    # ---------------------------------------------------- device callbacks

    def _subscribe_voice_assistant(self, client: APIClient) -> None:
        if self._unsub_va is not None:
            self._unsub_va()
        self._occupied_by = None
        self._rejection_seen = False
        self._unsub_va = client.subscribe_voice_assistant(
            handle_start=self._handle_start,
            handle_stop=self._handle_stop,
            handle_audio=self._handle_audio,
            handle_announcement_finished=self._handle_announcement_finished,
        )

    async def _handle_start(
        self,
        conversation_id: str,
        flags: int,
        audio_settings: Any,
        wake_word_phrase: str | None,
    ) -> int | None:
        if wake_word_phrase:
            _LOGGER.info("聽到喚醒詞「%s」", wake_word_phrase)
        self._set_streaming(True)
        # Light up the ring once the device has our reply (port 0 = send audio over the API).
        asyncio.get_running_loop().call_later(0.1, self.indicate_listening)
        return 0

    async def _handle_stop(self, abort: bool) -> None:
        if self.streaming:
            _LOGGER.info("Voice PE 停止了收音（按了中央按鈕或說了喚醒詞？），稍後自動恢復")
            self._set_streaming(False)

    async def _handle_audio(self, data: bytes, data2: bytes | None = None) -> None:
        # data is the enhanced channel (echo-cancelled, noise-suppressed by the
        # Voice PE's XMOS chip); data2, on newer firmware, is the raw one.
        if self.streaming:
            self._listener.on_audio(data)

    async def _handle_announcement_finished(self, finished: Any) -> None:
        _LOGGER.debug("Announcement finished: %s", finished)

    def _on_state(self, state: Any) -> None:
        if self._mute_key is None or state.key != self._mute_key:
            return
        if not isinstance(state, SwitchState) or state.state == self.muted:
            return
        first = self.muted is None
        self.muted = state.state
        self._changed.set()
        if self.muted:
            if not first:
                _LOGGER.info("Voice PE 已靜音")
            if self.streaming:
                # End the run so the ring shows the red "muted" light instead of "listening".
                self._end_run()
                self._set_streaming(False)
        elif not first:
            _LOGGER.info("Voice PE 已取消靜音")

    def _on_log(self, msg: Any) -> None:
        text = _ANSI_RE.sub("", msg.message.decode("utf-8", "replace")).strip()
        if self._device_logs:
            _LOGGER.debug("[裝置] %s", text)
        # The rejection is logged as one message (new firmware) or as several
        # lines (old firmware): remember the marker until "Current client" shows up.
        if OCCUPIED_MARKER in text:
            self._rejection_seen = True
        if not self._rejection_seen or not (current := _CURRENT_CLIENT_RE.search(text)):
            return
        self._rejection_seen = False
        holder = current.group(1).strip()
        if holder.startswith(CLIENT_NAME):
            # We hold the voice assistant; someone else (usually Home Assistant) was turned away.
            _LOGGER.warning(
                "另一個程式（通常是 Home Assistant）也想使用 Voice PE 的語音助理，"
                "但現在由本程式使用中；結束本程式後，請在 Home Assistant 重新載入這台裝置"
            )
            return
        self._occupied_by = holder
        self._changed.set()

    def _end_run(self) -> None:
        if self._client is None:
            return
        try:
            self._client.send_voice_assistant_event(
                VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END, None
            )
        except APIConnectionError:
            pass

    # -------------------------------------------------------- LED feedback

    def indicate_listening(self) -> None:
        """Ring: slow spin ("waiting for command")."""
        self._send_event(VoiceAssistantEventType.VOICE_ASSISTANT_STT_START)

    def indicate_speech(self) -> None:
        """Ring: fast spin ("listening to a command")."""
        self._send_event(VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_START)

    def _send_event(self, event_type: VoiceAssistantEventType) -> None:
        if not self._led_feedback or not self.streaming or self._client is None:
            return
        try:
            self._client.send_voice_assistant_event(event_type, None)
        except APIConnectionError:
            pass
