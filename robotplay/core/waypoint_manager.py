"""
WaypointManager — the single source of truth for the taught data.

It holds two clearly-separated things (per the teaching model):

    • waypoints    — the poses the operator explicitly captured with the
                     "Point & Play" button. Their straight-line connections form
                     the WAYPOINT PATH — the intended (ideal Cartesian) robot
                     trajectory.
    • motion_trail — a rolling record of where the tracker actually moved
                     (freehand). This is a *separate* visualisation: it can be
                     curvy and shows how the hand moved, not where the robot goes.

The manager is pure data + numpy accessors — no Qt, no hardware — so it is easy
to test and reuse. It emits nothing; callers pull arrays each render frame.
"""

from __future__ import annotations

import math

import numpy as np

from ..config import CONFIG
from .models import TrackerData, Waypoint


class WaypointManager:
    def __init__(self):
        self.waypoints: list[Waypoint] = []
        self._trail: list[tuple[float, float, float]] = []
        self._max_trail = CONFIG.capture.max_trail_points
        self._min_trail = CONFIG.capture.min_trail_dist
        self._next_number = 1

    # ── waypoints ────────────────────────────────────────────────
    def capture(self, pose: TrackerData, name: str = "") -> Waypoint:
        """Record the current pose as a new numbered waypoint."""
        wp = Waypoint(number=self._next_number, pose=pose.copy(), name=name)
        self.waypoints.append(wp)
        self._next_number += 1
        return wp

    def delete(self, index: int) -> bool:
        if 0 <= index < len(self.waypoints):
            self.waypoints.pop(index)
            self._renumber()
            return True
        return False

    def delete_last(self) -> bool:
        if self.waypoints:
            self.waypoints.pop()
            self._renumber()
            return True
        return False

    def rename(self, index: int, name: str) -> bool:
        if 0 <= index < len(self.waypoints):
            self.waypoints[index].name = name
            return True
        return False

    def move(self, index: int, new_index: int) -> bool:
        """Reorder a waypoint (for the 'reorder' table action)."""
        if 0 <= index < len(self.waypoints) and 0 <= new_index < len(self.waypoints):
            wp = self.waypoints.pop(index)
            self.waypoints.insert(new_index, wp)
            self._renumber()
            return True
        return False

    def clear_waypoints(self) -> None:
        self.waypoints.clear()
        self._next_number = 1

    def _renumber(self) -> None:
        """Keep waypoint numbers contiguous after edits; preserve custom names."""
        for i, wp in enumerate(self.waypoints, 1):
            if wp.name == f"P{wp.number:02d}":   # still a default name
                wp.name = f"P{i:02d}"
            wp.number = i
        self._next_number = len(self.waypoints) + 1

    # ── motion trail ─────────────────────────────────────────────
    def push_trail(self, pose: TrackerData) -> None:
        p = (pose.x, pose.y, pose.z)
        if not self._trail or math.dist(self._trail[-1], p) >= self._min_trail:
            self._trail.append(p)
            if len(self._trail) > self._max_trail:
                self._trail.pop(0)

    def clear_trail(self) -> None:
        self._trail.clear()

    def clear_all(self) -> None:
        self.clear_waypoints()
        self.clear_trail()

    # ── numpy accessors for the 3D view ─────────────────────────
    def waypoint_positions(self) -> np.ndarray:
        if not self.waypoints:
            return np.zeros((0, 3))
        return np.array([wp.pose.position for wp in self.waypoints])

    def path_segments(self) -> np.ndarray:
        """Straight waypoint path as a poly-line (>=2 points) or empty."""
        if len(self.waypoints) < 2:
            return np.zeros((0, 3))
        return np.array([wp.pose.position for wp in self.waypoints])

    def trail_array(self) -> np.ndarray:
        if len(self._trail) < 2:
            return np.zeros((0, 3))
        return np.array(self._trail)

    # ── convenience ─────────────────────────────────────────────
    @property
    def count(self) -> int:
        return len(self.waypoints)

    def poses(self) -> list[TrackerData]:
        return [wp.pose for wp in self.waypoints]
