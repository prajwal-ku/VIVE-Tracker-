"""
PlaybackControls — transport bar + progress + live playback read-out.

Emits high-level intents (play / pause / stop / replay / speed changed); the main
window drives the `PlaybackEngine` and calls back into `set_frame` / `set_state`
each render frame to refresh the progress bar and coordinate read-out.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider,
    QProgressBar,
)

from ..config import CONFIG
from ..core.models import TrackerData
from ..core.playback_engine import PlaybackState


class PlaybackControls(QGroupBox):
    play_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    replay_clicked = pyqtSignal()
    speed_changed = pyqtSignal(float)   # metres / second

    def __init__(self):
        super().__init__("Playback")
        v = QVBoxLayout(self)
        v.setSpacing(6)

        row = QHBoxLayout()
        self._btn_play = QPushButton("▶ Play")
        self._btn_play.setObjectName("btn_play")
        self._btn_pause = QPushButton("⏸ Pause")
        self._btn_stop = QPushButton("⏹ Stop")
        self._btn_replay = QPushButton("↻ Replay")
        self._btn_play.clicked.connect(self.play_clicked)
        self._btn_pause.clicked.connect(self.pause_clicked)
        self._btn_stop.clicked.connect(self.stop_clicked)
        self._btn_replay.clicked.connect(self.replay_clicked)
        for b in (self._btn_play, self._btn_pause, self._btn_stop, self._btn_replay):
            row.addWidget(b)
        v.addLayout(row)

        # Speed
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Speed:"))
        self._speed = QSlider(Qt.Orientation.Horizontal)
        pc = CONFIG.playback
        self._speed.setRange(int(pc.speed_min * 100), int(pc.speed_max * 100))
        self._speed.setValue(int(pc.default_speed * 100))
        self._speed.valueChanged.connect(self._on_speed)
        self._speed_lbl = QLabel(f"{pc.default_speed:.2f} m/s")
        self._speed_lbl.setObjectName("hint")
        self._speed_lbl.setFixedWidth(70)
        srow.addWidget(self._speed)
        srow.addWidget(self._speed_lbl)
        v.addLayout(srow)

        # Progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%p%")
        v.addWidget(self._progress)

        # Live read-out
        self._state_lbl = QLabel("State: idle")
        self._state_lbl.setObjectName("hint")
        self._coords = QLabel("—")
        self._coords.setObjectName("mono")
        v.addWidget(self._state_lbl)
        v.addWidget(self._coords)

    def _on_speed(self, val: int) -> None:
        mps = val / 100.0
        self._speed_lbl.setText(f"{mps:.2f} m/s")
        self.speed_changed.emit(mps)

    # ── driven by the main window each frame ────────────────────
    def set_state(self, state: PlaybackState) -> None:
        self._state_lbl.setText(f"State: {state.value}")
        playing = state == PlaybackState.PLAYING
        self._btn_play.setEnabled(state != PlaybackState.PLAYING)
        self._btn_pause.setText("⏸ Pause" if playing else "▶ Resume")

    def set_frame(self, pose: TrackerData, target_index: int,
                  target_name: str, progress: float) -> None:
        self._progress.setValue(int(progress * 1000))
        self._coords.setText(
            f"→ {target_name}   "
            f"X:{pose.x*1000:+.0f} Y:{pose.y*1000:+.0f} Z:{pose.z*1000:+.0f} mm\n"
            f"Roll:{pose.roll:+.1f}°  Pitch:{pose.pitch:+.1f}°  Yaw:{pose.yaw:+.1f}°")

    def reset(self) -> None:
        self._progress.setValue(0)
        self._coords.setText("—")
        self._state_lbl.setText("State: idle")
        self._btn_pause.setText("⏸ Pause")
        self._btn_play.setEnabled(True)
