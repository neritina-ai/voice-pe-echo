"""Console output: log lines plus a live status/level line at the bottom."""

from __future__ import annotations

import asyncio
import logging
import shutil
import threading
import time
import unicodedata
from collections.abc import Callable
from typing import TextIO

METER_WIDTH = 20
METER_FLOOR_DB = -60.0


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def level_bar(level_db: float) -> str:
    fraction = min(1.0, max(0.0, (level_db - METER_FLOOR_DB) / -METER_FLOOR_DB))
    filled = round(fraction * METER_WIDTH)
    return "[" + "#" * filled + "-" * (METER_WIDTH - filled) + "]"


class StatusLine:
    """A single line that is redrawn in place; log records are printed above it."""

    def __init__(self, stream: TextIO, enabled: bool) -> None:
        self._stream = stream
        self.enabled = enabled
        self._lock = threading.Lock()
        self._text = ""
        self._shown_width = 0

    def set(self, text: str) -> None:
        with self._lock:
            limit = shutil.get_terminal_size((80, 24)).columns - 1
            while display_width(text) > limit and text:
                text = text[:-1]
            self._text = text
            self._draw()

    def _draw(self) -> None:
        if not self.enabled:
            return
        width = display_width(self._text)
        pad = " " * max(0, self._shown_width - width)
        self._stream.write("\r" + self._text + pad)
        self._stream.flush()
        self._shown_width = width

    def _erase(self) -> None:
        if self.enabled and self._shown_width:
            self._stream.write("\r" + " " * self._shown_width + "\r")
            self._shown_width = 0

    def write_above(self, line: str) -> None:
        with self._lock:
            self._erase()
            self._stream.write(line + "\n")
            self._stream.flush()
            self._draw()

    def close(self) -> None:
        with self._lock:
            self._erase()
            self._stream.flush()
            self.enabled = False


class StatusAwareHandler(logging.Handler):
    def __init__(self, status: StatusLine) -> None:
        super().__init__()
        self._status = status

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._status.write_above(self.format(record))
        except Exception:
            self.handleError(record)


async def run_meter(
    status: StatusLine,
    state: Callable[[], str],
    level: Callable[[], tuple[float, float]],
    interval: float = 0.1,
) -> None:
    """Redraw the status line with a peak-hold level meter until cancelled."""
    peak = -100.0
    while True:
        level_db, level_time = level()
        if time.monotonic() - level_time > 1.0:
            level_db = -100.0  # no audio arriving
        peak = max(level_db, peak - 3.0)
        meter = f"{level_bar(peak)} {peak:6.1f} dBFS" if peak > -100 else f"{level_bar(-100)}   --.- dBFS"
        text = state()
        text += " " * max(0, 14 - display_width(text))
        status.set(f"狀態：{text} 音量 {meter}")
        await asyncio.sleep(interval)
