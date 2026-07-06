"""
PlaybackEngine — animate a virtual tracker along the taught waypoint path.

Playback follows the WAYPOINT PATH: straight Cartesian segments between recorded
waypoints (position interpolated linearly, orientation via slerp). This is the
"ideal robot trajectory" — the same path the robot backends execute.

The engine is a small, frame-driven state machine. It carries no timer of its
own: the main window ticks `update(dt)` every render frame and reads back the
current interpolated pose, the active waypoint, and overall progress. That keeps
all animation on the GUI thread and makes speed/pause/stop trivial.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from ..config import CONFIG
from .models import TrackerData, Waypoint, interpolate_pose


class PlaybackState(Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    FINISHED = "finished"


@dataclass
class PlaybackFrame:
    pose: TrackerData
    segment_index: int      # index of the waypoint we are moving AWAY from
    target_index: int       # index of the waypoint we are moving TOWARDS
    progress: float         # 0..1 over the whole path


class PlaybackEngine:
    def __init__(self):
        self._waypoints: list[Waypoint] = []
        self._seg_lengths: list[float] = []
        self._total_len = 0.0

        self.state = PlaybackState.IDLE
        self.speed = CONFIG.playback.default_speed   # metres / second
        self._distance = 0.0                          # metres travelled so far

    # ── control ──────────────────────────────────────────────────
    def load(self, waypoints: list[Waypoint]) -> bool:
        """Prepare a path. Needs >= 2 waypoints. Returns True if playable."""
        self._waypoints = [wp for wp in waypoints]
        self._seg_lengths = []
        self._total_len = 0.0
        for a, b in zip(self._waypoints, self._waypoints[1:]):
            d = float(np.linalg.norm(b.pose.position - a.pose.position))
            self._seg_lengths.append(d)
            self._total_len += d
        self._distance = 0.0
        self.state = PlaybackState.IDLE
        return len(self._waypoints) >= 2 and self._total_len > 1e-6

    def play(self) -> None:
        if self.state in (PlaybackState.IDLE, PlaybackState.FINISHED):
            self._distance = 0.0
        self.state = PlaybackState.PLAYING

    def pause(self) -> None:
        if self.state == PlaybackState.PLAYING:
            self.state = PlaybackState.PAUSED

    def resume(self) -> None:
        if self.state == PlaybackState.PAUSED:
            self.state = PlaybackState.PLAYING

    def toggle_pause(self) -> None:
        if self.state == PlaybackState.PLAYING:
            self.pause()
        elif self.state == PlaybackState.PAUSED:
            self.resume()

    def stop(self) -> None:
        self.state = PlaybackState.IDLE
        self._distance = 0.0

    def replay(self) -> None:
        self._distance = 0.0
        self.state = PlaybackState.PLAYING

    def set_speed(self, metres_per_sec: float) -> None:
        self.speed = max(CONFIG.playback.speed_min,
                         min(CONFIG.playback.speed_max, metres_per_sec))

    @property
    def is_active(self) -> bool:
        return self.state in (PlaybackState.PLAYING, PlaybackState.PAUSED)

    # ── frame update ─────────────────────────────────────────────
    def update(self, dt: float) -> PlaybackFrame | None:
        """Advance by dt seconds (only when PLAYING) and return the current
        frame. Returns None if there is nothing to play."""
        if not self._waypoints or self._total_len <= 1e-6:
            return None
        if self.state == PlaybackState.PLAYING:
            self._distance += self.speed * dt
            if self._distance >= self._total_len:
                self._distance = self._total_len
                self.state = PlaybackState.FINISHED
        return self._frame_at(self._distance)

    def _frame_at(self, distance: float) -> PlaybackFrame:
        """Map a travelled distance to a pose along the poly-line."""
        distance = max(0.0, min(self._total_len, distance))
        acc = 0.0
        for i, seg in enumerate(self._seg_lengths):
            if seg <= 1e-9:
                continue
            if distance <= acc + seg:
                t = (distance - acc) / seg
                pose = interpolate_pose(self._waypoints[i].pose,
                                        self._waypoints[i + 1].pose, t)
                return PlaybackFrame(
                    pose=pose, segment_index=i, target_index=i + 1,
                    progress=distance / self._total_len)
            acc += seg
        # At (or beyond) the end.
        last = len(self._waypoints) - 1
        return PlaybackFrame(pose=self._waypoints[last].pose.copy(),
                             segment_index=last, target_index=last,
                             progress=1.0)
