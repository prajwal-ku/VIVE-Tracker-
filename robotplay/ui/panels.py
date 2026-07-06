"""
Reusable side-panel widgets:

    • StatusDot            — a coloured green/amber/red indicator
    • ConnectionStatusPanel— SteamVR / Tracker / Hardware / Base stations health
    • LivePosePanel        — continuously refreshed X/Y/Z + Roll/Pitch/Yaw
    • EventLogPanel        — timestamped, colour-coded event feed
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QGroupBox, QHBoxLayout, QVBoxLayout, QLabel, QWidget, QTextEdit,
    QGridLayout,
)

from ..config import CONFIG
from ..core.logger import LogEntry, LogLevel
from ..core.models import TrackerData
from ..tracker.base import TrackerStatus, DeviceState


_STATE_COLOR = {
    DeviceState.OK:      CONFIG.palette.ok,
    DeviceState.WARN:    CONFIG.palette.warn,
    DeviceState.ERROR:   CONFIG.palette.err,
    DeviceState.OFFLINE: "#484f58",
}
_STATE_TEXT = {
    DeviceState.OK:      "OK",
    DeviceState.WARN:    "WARN",
    DeviceState.ERROR:   "ERROR",
    DeviceState.OFFLINE: "OFFLINE",
}


class StatusDot(QLabel):
    """A small round colour indicator."""

    def __init__(self, diameter: int = 12):
        super().__init__()
        self._d = diameter
        self.setFixedSize(diameter, diameter)
        self.set_state(DeviceState.OFFLINE)

    def set_state(self, state: DeviceState) -> None:
        c = _STATE_COLOR[state]
        self.setStyleSheet(
            f"background:{c}; border-radius:{self._d // 2}px; "
            f"border:1px solid #00000055;")
        self.setToolTip(_STATE_TEXT[state])


class _StatusRow(QWidget):
    def __init__(self, label: str):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 1)
        self.dot = StatusDot()
        name = QLabel(label)
        self.value = QLabel("—")
        self.value.setObjectName("hint")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.dot)
        lay.addWidget(name)
        lay.addStretch()
        lay.addWidget(self.value)


class ConnectionStatusPanel(QGroupBox):
    """Green/red health board for the tracking system."""

    def __init__(self):
        super().__init__("Connection Status")
        v = QVBoxLayout(self)
        v.setSpacing(2)
        self._rows = {
            "steamvr": _StatusRow("SteamVR"),
            "tracker": _StatusRow("Tracker"),
            "hardware": _StatusRow("Hardware Buttons"),
            "base1": _StatusRow("Base Station 1"),
            "base2": _StatusRow("Base Station 2"),
        }
        for row in self._rows.values():
            v.addWidget(row)

    def update_status(self, st: TrackerStatus) -> None:
        def apply(key, state, text=None, tip=None):
            row = self._rows[key]
            row.dot.set_state(state)
            row.value.setText(text if text is not None else _STATE_TEXT[state])
            if tip:
                row.setToolTip(tip)

        apply("steamvr", st.steamvr)

        batt = f" · {int(st.battery*100)}%" if st.battery is not None else ""
        apply("tracker", st.tracker, _STATE_TEXT[st.tracker] + batt, st.detail)

        # Hardware buttons are considered OK whenever the tracker is tracking.
        hw = DeviceState.OK if st.tracker == DeviceState.OK else (
            DeviceState.OFFLINE if st.tracker == DeviceState.OFFLINE
            else DeviceState.WARN)
        apply("hardware", hw)
        apply("base1", st.base_station_1)
        apply("base2", st.base_station_2)


class LivePosePanel(QGroupBox):
    """Continuously updated position + orientation read-out."""

    def __init__(self):
        super().__init__("Live Pose")
        grid = QGridLayout(self)
        grid.setVerticalSpacing(3)
        grid.setHorizontalSpacing(10)

        self._fields: dict[str, QLabel] = {}
        labels = [("X", "m"), ("Y", "m"), ("Z", "m"),
                  ("Roll", "°"), ("Pitch", "°"), ("Yaw", "°")]
        for i, (name, unit) in enumerate(labels):
            r, c = divmod(i, 2)
            cell = QLabel(f"{name}: —")
            cell.setObjectName("mono")
            self._fields[name] = cell
            grid.addWidget(cell, r, c)
        self._units = dict(labels)

    def update_pose(self, pose: TrackerData) -> None:
        f = self._fields
        f["X"].setText(f"X: {pose.x*1000:+8.1f} mm")
        f["Y"].setText(f"Y: {pose.y*1000:+8.1f} mm")
        f["Z"].setText(f"Z: {pose.z*1000:+8.1f} mm")
        f["Roll"].setText(f"Roll: {pose.roll:+7.1f}°")
        f["Pitch"].setText(f"Pitch: {pose.pitch:+6.1f}°")
        f["Yaw"].setText(f"Yaw: {pose.yaw:+7.1f}°")

    def set_no_signal(self) -> None:
        for name, cell in self._fields.items():
            cell.setText(f"{name}: —")


class EventLogPanel(QGroupBox):
    """Colour-coded, timestamped event feed driven by the EventLogger signal."""

    _LEVEL_COLOR = {
        LogLevel.INFO:  CONFIG.palette.text_dim,
        LogLevel.EVENT: CONFIG.palette.mono_green,
        LogLevel.WARN:  CONFIG.palette.warn,
        LogLevel.ERROR: CONFIG.palette.err,
    }

    def __init__(self):
        super().__init__("Event Log")
        v = QVBoxLayout(self)
        self._view = QTextEdit()
        self._view.setReadOnly(True)
        v.addWidget(self._view)

    def append_entry(self, entry: LogEntry) -> None:
        color = self._LEVEL_COLOR.get(entry.level, CONFIG.palette.text)
        level = f"{entry.level.value:<5}"
        message = (entry.message.replace("&", "&amp;")
                                .replace("<", "&lt;").replace(">", "&gt;"))
        self._view.append(
            f'<span style="color:#6e7681">[{entry.time}]</span> '
            f'<span style="color:{color}">{level} {message}</span>')
        sb = self._view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear(self) -> None:
        self._view.clear()
