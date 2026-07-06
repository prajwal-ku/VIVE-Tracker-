"""
SessionManager — persistence and export for a teaching session.

Operates on a `WaypointManager` and knows nothing about the UI. It provides:

    • Save / Load session   → JSON (round-trips waypoints + motion trail)
    • Export JSON           → same as save (explicit menu action)
    • Export CSV            → one row per waypoint for spreadsheets / robot tools

Keeping this in one place means new formats (URDF, ROS bag, robot-native program)
can be added without touching the rest of the app.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime

from .. import __version__
from .models import Waypoint
from .waypoint_manager import WaypointManager


class SessionManager:
    def __init__(self, waypoints: WaypointManager):
        self._wm = waypoints

    # ── save / load ──────────────────────────────────────────────
    def save(self, filepath: str) -> None:
        data = {
            "app": "Robot Point & Play",
            "version": __version__,
            "saved": datetime.now().isoformat(timespec="seconds"),
            "waypoints": [wp.as_dict() for wp in self._wm.waypoints],
            "motion_trail": [list(p) for p in self._wm.trail_array().tolist()],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, filepath: str) -> int:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._wm.clear_all()
        for d in data.get("waypoints", []):
            wp = Waypoint.from_dict(d)
            self._wm.waypoints.append(wp)
        # Re-seed the numbering counter after a load.
        self._wm._next_number = len(self._wm.waypoints) + 1
        for p in data.get("motion_trail", []):
            if len(p) == 3:
                self._wm._trail.append(tuple(p))
        return len(self._wm.waypoints)

    # ── exports ──────────────────────────────────────────────────
    def export_json(self, filepath: str) -> None:
        self.save(filepath)

    def export_csv(self, filepath: str) -> None:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["number", "name", "timestamp",
                        "x_m", "y_m", "z_m",
                        "roll_deg", "pitch_deg", "yaw_deg",
                        "qw", "qx", "qy", "qz"])
            for wp in self._wm.waypoints:
                p = wp.pose
                w.writerow([wp.number, wp.name, wp.timestamp,
                            f"{p.x:.6f}", f"{p.y:.6f}", f"{p.z:.6f}",
                            f"{p.roll:.3f}", f"{p.pitch:.3f}", f"{p.yaw:.3f}",
                            f"{p.qw:.6f}", f"{p.qx:.6f}", f"{p.qy:.6f}", f"{p.qz:.6f}"])
