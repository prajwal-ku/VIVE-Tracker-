"""
Timestamped event logger.

The logger is UI-agnostic: it stores entries and emits a Qt signal whenever a new
one arrives. The Event Log panel subscribes to that signal, so any part of the
app (trackers, robot drivers, playback engine) can log an event without knowing
anything about widgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from PyQt6.QtCore import QObject, pyqtSignal


class LogLevel(Enum):
    INFO = "INFO"
    EVENT = "EVENT"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass
class LogEntry:
    time: str
    level: LogLevel
    message: str

    def formatted(self) -> str:
        return f"[{self.time}] {self.level.value:<5} {self.message}"


class EventLogger(QObject):
    """Central event log. Emits `entry_added` for every new entry."""

    entry_added = pyqtSignal(object)   # LogEntry

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[LogEntry] = []

    # ── logging api ──────────────────────────────────────────────
    def log(self, message: str, level: LogLevel = LogLevel.INFO) -> LogEntry:
        entry = LogEntry(datetime.now().strftime("%H:%M:%S"), level, message)
        self._entries.append(entry)
        self.entry_added.emit(entry)
        return entry

    def info(self, msg: str) -> LogEntry:  return self.log(msg, LogLevel.INFO)
    def event(self, msg: str) -> LogEntry: return self.log(msg, LogLevel.EVENT)
    def warn(self, msg: str) -> LogEntry:  return self.log(msg, LogLevel.WARN)
    def error(self, msg: str) -> LogEntry: return self.log(msg, LogLevel.ERROR)

    # ── access / export ──────────────────────────────────────────
    @property
    def entries(self) -> list[LogEntry]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def dump_text(self) -> str:
        return "\n".join(e.formatted() for e in self._entries)
