"""
Viewport3D — the embedded 3D workspace (pyqtgraph OpenGL).

Renders the industrial-offline-programming-style scene:

    • ground grid + world XYZ axes (X red, Y green, Z blue) with labels
    • the live tracker as a bright marker plus an orientation triad
    • the freehand MOTION TRAIL (cyan poly-line — how the hand actually moved)
    • recorded WAYPOINTS as gold spheres with numeric labels
    • the WAYPOINT PATH as straight white segments (intended robot trajectory)
    • a playback ghost that animates along the path, highlighting the current wp

The tracker marker follows the live VIVE Tracker pose; when there is no valid
signal it is hidden. Camera orbit/zoom/pan use the standard pyqtgraph GL controls.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph.opengl as gl
from PyQt6.QtCore import QTimer

from ..config import CONFIG
from ..core.models import TrackerData


class Viewport3D(gl.GLViewWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg = CONFIG.scene
        self._pal = CONFIG.palette
        self.setBackgroundColor(self._pal.scene_bg)
        self.setCameraPosition(distance=self._cfg.cam_distance,
                               elevation=self._cfg.cam_elevation,
                               azimuth=self._cfg.cam_azimuth)

        self._label_items: list[gl.GLTextItem] = []

        self._build_static_scene()
        self._build_dynamic_items()

    # ── static scene: grid + axes ───────────────────────────────
    def _build_static_scene(self) -> None:
        s = self._cfg.workspace_size
        grid = gl.GLGridItem()
        grid.setSize(s, s)
        grid.setSpacing(self._cfg.grid_spacing, self._cfg.grid_spacing)
        grid.setColor(tuple(int(c * 255) for c in self._pal.grid_rgba))
        self.addItem(grid)

        L = self._cfg.axis_length
        for pts, col, label in [
            (np.array([[0, 0, 0], [L, 0, 0]]), self._pal.axis_x_rgba, "X"),
            (np.array([[0, 0, 0], [0, L, 0]]), self._pal.axis_y_rgba, "Y"),
            (np.array([[0, 0, 0], [0, 0, L]]), self._pal.axis_z_rgba, "Z"),
        ]:
            self.addItem(gl.GLLinePlotItem(pos=pts, color=col, width=2,
                                           antialias=True))
            tip = pts[1] * 1.05
            self.addItem(gl.GLTextItem(pos=tip, text=label,
                                       color=tuple(int(c * 255) for c in col)))

    # ── dynamic items ───────────────────────────────────────────
    def _build_dynamic_items(self) -> None:
        # Live tracker marker (starts hidden until a valid pose arrives)
        self._tracker = gl.GLScatterPlotItem(
            pos=np.array([[0.0, 0.0, -999.0]]),
            color=self._pal.tracker_rgba, size=self._cfg.tracker_size, pxMode=True)
        self.addItem(self._tracker)

        # Orientation triad (3 body axes as line pairs)
        self._triad = gl.GLLinePlotItem(pos=np.zeros((6, 3)),
                                        color=np.ones((6, 4)),
                                        width=3, antialias=True, mode="lines")
        self.addItem(self._triad)

        # Motion trail (cyan)
        self._trail = gl.GLLinePlotItem(pos=np.zeros((2, 3)),
                                        color=self._pal.trail_rgba,
                                        width=1.4, antialias=True)
        self.addItem(self._trail)

        # Waypoint path (straight white segments)
        self._path = gl.GLLinePlotItem(pos=np.zeros((2, 3)),
                                       color=self._pal.wp_path_rgba,
                                       width=3.0, antialias=True)
        self.addItem(self._path)

        # Waypoint markers (gold)
        self._waypoints = gl.GLScatterPlotItem(
            pos=np.zeros((0, 3)), color=self._pal.waypoint_rgba,
            size=self._cfg.waypoint_size, pxMode=True)
        self.addItem(self._waypoints)

        # Playback ghost (magenta) — hidden until playing
        self._ghost = gl.GLScatterPlotItem(
            pos=np.array([[0.0, 0.0, -999.0]]), color=self._pal.playback_rgba,
            size=self._cfg.tracker_size + 6, pxMode=True)
        self.addItem(self._ghost)

        # Highlight ring for the current playback waypoint
        self._highlight = gl.GLScatterPlotItem(
            pos=np.array([[0.0, 0.0, -999.0]]), color=self._pal.highlight_rgba,
            size=self._cfg.waypoint_size + 12, pxMode=True)
        self.addItem(self._highlight)

    # ── live updates (called every render frame) ────────────────
    def update_tracker(self, pose: TrackerData, valid: bool = True) -> None:
        if not valid:
            # No tracking signal — hide the marker and orientation triad.
            self._tracker.setData(pos=np.array([[0.0, 0.0, -999.0]]))
            self._triad.setData(pos=np.zeros((6, 3)), color=np.zeros((6, 4)))
            return
        p = pose.position
        self._tracker.setData(pos=np.array([p]),
                             color=self._pal.tracker_rgba,
                             size=self._cfg.tracker_size)
        self._triad.setData(pos=self._triad_points(pose),
                            color=self._triad_colors())

    def _triad_points(self, pose: TrackerData) -> np.ndarray:
        o = pose.position
        R = pose.rotation_matrix
        L = self._cfg.triad_length
        pts = []
        for axis in range(3):
            pts.append(o)
            pts.append(o + R[:, axis] * L)
        return np.array(pts)

    def _triad_colors(self) -> np.ndarray:
        cols = []
        for col in (self._pal.axis_x_rgba, self._pal.axis_y_rgba,
                    self._pal.axis_z_rgba):
            cols.append(col); cols.append(col)
        return np.array(cols)

    def update_trail(self, arr: np.ndarray) -> None:
        if len(arr) >= 2:
            self._trail.setData(pos=arr)
        else:
            self._trail.setData(pos=np.zeros((2, 3)))

    def update_waypoints(self, positions: np.ndarray, labels: list[str]) -> None:
        if len(positions) == 0:
            self._waypoints.setData(pos=np.zeros((0, 3)))
        else:
            self._waypoints.setData(pos=positions)
        self._sync_labels(positions, labels)

    def update_path(self, segments: np.ndarray) -> None:
        if len(segments) >= 2:
            self._path.setData(pos=segments)
        else:
            self._path.setData(pos=np.zeros((2, 3)))

    def _sync_labels(self, positions: np.ndarray, labels: list[str]) -> None:
        """Create/destroy GLTextItems so there is exactly one per waypoint."""
        n = len(labels)
        while len(self._label_items) < n:
            it = gl.GLTextItem(pos=np.zeros(3), text="",
                               color=(255, 210, 90, 255))
            self.addItem(it)
            self._label_items.append(it)
        while len(self._label_items) > n:
            it = self._label_items.pop()
            self.removeItem(it)
        for i in range(n):
            off = np.array([0.03, 0.03, 0.03])
            self._label_items[i].setData(pos=positions[i] + off, text=labels[i])

    # ── playback visuals ────────────────────────────────────────
    def set_ghost(self, pose: TrackerData | None) -> None:
        if pose is None:
            self._ghost.setData(pos=np.array([[0.0, 0.0, -999.0]]))
        else:
            self._ghost.setData(pos=np.array([pose.position]))

    def set_highlight(self, position: np.ndarray | None) -> None:
        if position is None:
            self._highlight.setData(pos=np.array([[0.0, 0.0, -999.0]]))
        else:
            self._highlight.setData(pos=np.array([position]))

    def flash_tracker(self) -> None:
        """Brief gold flash when a waypoint is captured."""
        self._tracker.setData(color=(1.0, 0.9, 0.0, 1.0),
                              size=self._cfg.tracker_size + 8)
        QTimer.singleShot(180, lambda: self._tracker.setData(
            color=self._pal.tracker_rgba, size=self._cfg.tracker_size))
