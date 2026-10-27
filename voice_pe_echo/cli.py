"""Command line entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from zeroconf.asyncio import AsyncZeroconf

from . import __version__
from .app import EchoApp
from .console import StatusAwareHandler, StatusLine, run_meter
from .device import DEFAULT_PORT, DEFAULT_START_SOUND, FatalDeviceError, VoicePE
from .discovery import discover
from .player import Player, PlayerError, list_output_devices
from .segmenter import Segmenter, SegmenterConfig
from .vad import create_vad

DEFAULT_CONFIG = "voice-pe-echo.toml"

_LOGGER = logging.getLogger("voice_pe_echo")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="voice-pe-echo",
        description="24 小時收音：Voice PE 聽到的每一句話，都從電腦喇叭原音重播。",
        epilog="詳細說明請見 docs/user-guide.md",
    )
    conn = p.add_argument_group("連線")
    conn.add_argument("--host", help="Voice PE 的 IP 或主機名稱；省略時自動在區網搜尋")
    conn.add_argument("--port", type=int, default=DEFAULT_PORT, help="ESPHome API 連接埠（預設 6053）")
    conn.add_argument("--key", help="API 加密金鑰（base64）；也可用環境變數 VOICE_PE_KEY 或設定檔")
    conn.add_argument("--discover", action="store_true", help="列出區網內的 ESPHome 裝置後結束")

    play = p.add_argument_group("播放")
    play.add_argument("--list-devices", action="store_true", help="列出電腦的音訊輸出裝置後結束")
    play.add_argument("--output-device", help="播放用的輸出裝置（--list-devices 顯示的編號或名稱的一部分）")
    play.add_argument("--volume", type=float, default=1.0, help="播放音量倍率（預設 1.0）")
    play.add_argument("--no-normalize", action="store_true", help="不要自動把音量調整到一致")
    play.add_argument("--save-dir", help="把每一句話另存成 WAV 檔的資料夾")

    det = p.add_argument_group("偵測與防回授")
    det.add_argument("--guard", type=float, default=0.6, help="播放結束後再忽略麥克風幾秒（預設 0.6）")
    det.add_argument("--silence", type=float, default=0.8, help="安靜多久算一句話說完（秒，預設 0.8）")
    det.add_argument("--max-sentence", type=float, default=20.0, help="一句話最長幾秒（預設 20）")
    det.add_argument("--threshold", type=float, default=0.5, help="語音判斷門檻 0~1，越高越不敏感（預設 0.5）")
    det.add_argument("--vad", choices=["auto", "silero", "energy"], default="auto", help="語音偵測方式")

    misc = p.add_argument_group("其他")
    misc.add_argument("--config", help=f"設定檔路徑（預設：目前資料夾的 {DEFAULT_CONFIG}）")
    misc.add_argument("--no-led", action="store_true", help="不要用 Voice PE 的燈環顯示收音狀態")
    misc.add_argument("--no-meter", action="store_true", help="不要顯示即時音量列")
    misc.add_argument("--start-sound", default=DEFAULT_START_SOUND, help=argparse.SUPPRESS)
    misc.add_argument("-v", "--verbose", action="count", default=0, help="顯示除錯訊息（-vv 更多）")
    misc.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def load_config(parser: argparse.ArgumentParser, path: str | None) -> dict[str, Any]:
    """Read the TOML config file; its keys are the long option names."""
    config_path = Path(path or DEFAULT_CONFIG)
    if not config_path.is_file():
        if path:
            parser.error(f"找不到設定檔 {config_path}")
        return {}
    try:
        with config_path.open("rb") as fp:
            raw = tomllib.load(fp)
    except tomllib.TOMLDecodeError as err:
        parser.error(f"設定檔 {config_path} 格式錯誤：{err}")
    known = {action.dest for action in parser._actions}
    config: dict[str, Any] = {}
    for name, value in raw.items():
        dest = name.replace("-", "_")
        if dest not in known or dest in {"config", "help", "version", "discover", "list_devices"}:
            parser.error(f"設定檔 {config_path} 有不認得的設定：{name}")
        if value != "":
            config[dest] = value
    return config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    pre, _rest = parser.parse_known_args(argv)
    defaults = load_config(parser, pre.config)
    for dest, env in (("host", "VOICE_PE_HOST"), ("key", "VOICE_PE_KEY")):
        if os.environ.get(env):
            defaults[dest] = os.environ[env]
    parser.set_defaults(**defaults)
    args = parser.parse_args(argv)
    if args.volume <= 0:
        parser.error("--volume 必須大於 0")
    if not 0 < args.threshold < 1:
        parser.error("--threshold 必須介於 0 和 1 之間")
    if args.guard < 0 or args.silence <= 0 or args.max_sentence <= 1:
        parser.error("--guard / --silence / --max-sentence 的值不合理")
    return args


class _Formatter(logging.Formatter):
    PREFIX = {logging.WARNING: "【注意】", logging.ERROR: "【錯誤】", logging.CRITICAL: "【錯誤】"}

    def format(self, record: logging.LogRecord) -> str:
        record.prefix = self.PREFIX.get(record.levelno, "")
        return super().format(record)


def setup_logging(verbose: int, status: StatusLine) -> None:
    handler = StatusAwareHandler(status)
    handler.setFormatter(_Formatter("%(asctime)s %(prefix)s%(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    if verbose:
        _LOGGER.setLevel(logging.DEBUG)
    library_level = logging.DEBUG if verbose >= 2 else logging.ERROR
    for name in ("aioesphomeapi", "zeroconf"):
        logging.getLogger(name).setLevel(library_level)


async def _discover_command(aiozc: AsyncZeroconf) -> int:
    print("搜尋區網內的 ESPHome 裝置（約 3 秒）…")
    devices = await discover(aiozc)
    if not devices:
        print("找不到任何 ESPHome 裝置。請確認裝置已上線，且電腦與裝置在同一個網路。")
        return 1
    for device in devices:
        mark = "Voice PE" if device.is_voice_pe else "其他裝置"
        print(f"  [{mark}] {device.describe()}")
    return 0


async def _find_target(
    args: argparse.Namespace, aiozc: AsyncZeroconf
) -> tuple[str, list[str] | None, int] | None:
    if args.host:
        return args.host, None, args.port
    _LOGGER.info("沒有指定 --host，搜尋區網內的 Voice PE…")
    devices = await discover(aiozc)
    voices = [d for d in devices if d.is_voice_pe]
    if not voices:
        _LOGGER.error(
            "找不到 Voice PE。請確認它已通電並連上 Wi-Fi、電腦和它在同一個網路，"
            "或用 --host 直接指定它的 IP。"
        )
        return None
    if len(voices) > 1:
        listing = "\n".join("  " + d.describe() for d in voices)
        _LOGGER.error("找到多台 Voice PE，請用 --host 指定要用哪一台：\n%s", listing)
        return None
    found = voices[0]
    _LOGGER.info("找到 %s", found.describe())
    if found.encryption == "key" and not args.key:
        _LOGGER.error(
            "這台 Voice PE 設有 API 加密金鑰，請用 --key 或設定檔提供。"
            "取得方式請見 docs/user-guide.md 附錄「取得加密金鑰」。"
        )
        return None
    if found.encryption == "none" and args.key:
        _LOGGER.warning("這台 Voice PE 沒有設定加密金鑰，忽略 --key")
        args.key = None
    return found.host or found.addresses[0], found.addresses or None, found.port


async def _run(args: argparse.Namespace, status: StatusLine) -> int:
    aiozc = AsyncZeroconf()
    try:
        if args.discover:
            return await _discover_command(aiozc)
        target = await _find_target(args, aiozc)
        if target is None:
            return 2
        host, addresses, port = target

        try:
            player = Player(args.output_device, volume=args.volume, normalize=not args.no_normalize)
        except PlayerError as err:
            _LOGGER.error("%s", err)
            return 2
        _LOGGER.info("播放裝置：%s", player.describe())
        vad = create_vad(args.vad)
        _LOGGER.debug("VAD: %s", vad.name)

        segmenter = Segmenter(
            SegmenterConfig(
                threshold=args.threshold,
                end_silence_s=args.silence,
                max_utterance_s=args.max_sentence,
            )
        )
        app = EchoApp(
            vad=vad,
            segmenter=segmenter,
            player=player,
            guard_s=args.guard,
            save_dir=Path(args.save_dir) if args.save_dir else None,
        )
        device = VoicePE(
            host,
            app,
            port=port,
            key=args.key,
            addresses=addresses,
            start_sound=args.start_sound,
            led_feedback=not args.no_led,
            device_logs=args.verbose >= 2,
            zeroconf_instance=aiozc,
        )
        app.device = device

        meter = None
        if status.enabled:
            meter = asyncio.create_task(
                run_meter(status, app.status_text, lambda: (app.level_db, app.level_time))
            )
        try:
            await device.run()
        except FatalDeviceError as err:
            _LOGGER.error("%s", err)
            return 2
        finally:
            if meter is not None:
                meter.cancel()
            await app.close()
        return 0
    finally:
        await aiozc.async_close()


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    args = parse_args(argv)
    if args.list_devices:
        try:
            print(list_output_devices())
        except PlayerError as err:
            print(err, file=sys.stderr)
            return 2
        print("（* 為系統預設裝置）")
        return 0

    interactive = sys.stdout.isatty() and not args.discover
    status = StatusLine(sys.stdout, enabled=interactive and not args.no_meter)
    setup_logging(args.verbose, status)
    try:
        return asyncio.run(_run(args, status))
    except KeyboardInterrupt:
        status.close()
        print("已結束。")
        return 0
    finally:
        status.close()
