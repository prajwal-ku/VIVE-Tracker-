"""
MainWindow — assembles every module into the application.

Runs on a real HTC VIVE Tracker (SteamVR/OpenVR) only — there is no simulated
pose source. On start it attempts to connect; the connection-status board and
live-pose panel reflect the true hardware state (nothing shows "OK" unless the
tracker is really tracking).

Teaching is hardware-driven: Pin 3 (Grip) captures a waypoint and Pin 4 (Trigger)
plays the taught path — there are no manual capture/play buttons and no robot
connection panel (robot execution is triggered from the hardware and will be
wired to the FAIRINO backend when the two machines merge). The window is a
visualisation console: a large 3D workspace flanked by tracker/calibration/status
panels and the waypoint table + event log.

Responsibilities (kept thin; the real work lives in the modules):
    • own the shared services (logger, waypoint/session/playback managers)
    • own the VIVE tracker driver and its connection lifecycle
    • drive three timers: render (pose + 3D + playback), hardware buttons, status
    • translate UI intents into calls on the managers, and refresh the views
    • load optional workspace / tracker CAD into the 3D scene (Scene menu)

The side columns live in scroll areas so a small screen scrolls instead of
overlapping, while a large monitor lays everything out neatly.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QPushButton, QLabel, QScrollArea, QFrame,
    QFileDialog, QMessageBox, QStatusBar, QSpinBox, QGridLayout,
)

from ..config import CONFIG
from ..core.logger import EventLogger
from ..core.waypoint_manager import WaypointManager
from ..core.session_manager import SessionManager
from ..core.playback_engine import PlaybackEngine, PlaybackState
from ..tracker import ViveTracker, DeviceState
from .style import build_stylesheet
from .viewport import Viewport3D
from .panels import ConnectionStatusPanel, LivePosePanel, EventLogPanel
from .waypoint_table import WaypointTable
from .playback_controls import PlaybackControls


class MainWindow(QMainWindow):
    # Cross-thread / deferred status messages.
    status_msg = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(CONFIG.window_title)
        self.resize(*CONFIG.window_size)
        self.setMinimumSize(1024, 600)

        # ── shared services ─────────────────────────────────────
        self.logger = EventLogger(self)
        self.waypoints = WaypointManager()
        self.session = SessionManager(self.waypoints)
        self.playback = PlaybackEngine()

        # ── VIVE tracker (the only pose source) ─────────────────
        self._vive = ViveTracker()
        self._tracker_ok = False
        self._reconnects = 0
        self._reconnect_logged = False

        # ── playback bookkeeping ────────────────────────────────
        self._last_frame_t = time.monotonic()
        self._prev_pb_state = PlaybackState.IDLE

        self.setStyleSheet(build_stylesheet())
        self._build_menu()
        self._build_ui()
        self._wire_signals()
        self._start_timers()

        self.logger.info("Application started — VIVE Tracker mode")
        # Try to connect to SteamVR / the tracker at launch.
        QTimer.singleShot(200, self._connect_tracker)

    # ══════════════════════════════════════════════════════════════
    #  UI construction
    # ══════════════════════════════════════════════════════════════
    def _build_menu(self) -> None:
        bar = self.menuBar()
        m = bar.addMenu("&Session")

        def act(name, slot, shortcut=None):
            a = QAction(name, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            m.addAction(a)
            return a

        act("&New Session", self._new_session, "Ctrl+N")
        act("&Save Session…", self._save_session, "Ctrl+S")
        act("&Load Session…", self._load_session, "Ctrl+O")
        m.addSeparator()
        act("Export &CSV…", self._export_csv)
        act("Export &JSON…", self._export_json)
        m.addSeparator()
        act("&Clear Session", self._clear_session)
        act("E&xit", self.close, "Ctrl+Q")

        s = bar.addMenu("Sce&ne")

        def sact(name, slot):
            a = QAction(name, self)
            a.triggered.connect(slot)
            s.addAction(a)
            return a

        sact("Load &Workspace CAD…", self._load_workspace_cad)
        sact("&Clear Workspace CAD", self._clear_workspace_cad)
        s.addSeparator()
        sact("Load &Tracker CAD…", self._load_tracker_cad)
        sact("&Reset Tracker CAD (VIVE 3.0)", self._reset_tracker_cad)

        h = bar.addMenu("&Help")
        ha = QAction("Controls & Shortcuts", self)
        ha.triggered.connect(self._show_help)
        h.addAction(ha)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        splitter.addWidget(self._build_left_column())
        splitter.addWidget(self._build_center_column())
        splitter.addWidget(self._build_right_column())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)   # the 3D workspace takes all extra room
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([320, 1160, 420])

        self._sb = QStatusBar()
        self.setStatusBar(self._sb)
        self._sb.showMessage("Ready — connect the VIVE Tracker")

    @staticmethod
    def _scroll(inner: QWidget, width: int) -> QScrollArea:
        """Wrap a column in a vertical scroll area so it never overlaps on a
        short screen but still expands on a tall one."""
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        # Vertical scroll is the point; horizontal only appears as a safety net.
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sa.setWidget(inner)
        sa.setFixedWidth(width)
        return sa

    def _build_left_column(self) -> QScrollArea:
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(8)

        v.addWidget(self._build_tracker_group())
        v.addWidget(self._build_calibration_group())
        self.status_panel = ConnectionStatusPanel()
        v.addWidget(self.status_panel)
        self.pose_panel = LivePosePanel()
        v.addWidget(self.pose_panel)

        pin = QLabel("Teaching is hardware-driven:\n"
                     "Pin 3 (Grip) = Capture waypoint   ·   Pin 4 (Trigger) = Play")
        pin.setObjectName("hint")
        pin.setWordWrap(True)
        v.addWidget(pin)
        v.addStretch()
        return self._scroll(inner, 320)

    def _build_tracker_group(self) -> QGroupBox:
        g = QGroupBox("VIVE Tracker")
        v = QVBoxLayout(g)
        v.setSpacing(6)

        self._tracker_lbl = QLabel("Not connected")
        self._tracker_lbl.setObjectName("hint")
        self._tracker_lbl.setWordWrap(True)
        v.addWidget(self._tracker_lbl)

        self._btn_conn_tracker = QPushButton("Connect Tracker")
        self._btn_conn_tracker.clicked.connect(self._toggle_tracker)
        v.addWidget(self._btn_conn_tracker)

        hint = QLabel("Requires SteamVR running with a paired tracker\n"
                      "and both base stations powered on.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)
        return g

    def _build_calibration_group(self) -> QGroupBox:
        g = QGroupBox("Calibration")
        v = QVBoxLayout(g)
        v.setSpacing(6)

        info = QLabel("Hold the tracker in the pose you want as HOME, then lock — "
                      "the UI axes adopt the tracker's own frame.")
        info.setObjectName("hint")
        info.setWordWrap(True)
        v.addWidget(info)

        row = QHBoxLayout()
        btn_zero = QPushButton("🔒  Calibrate · Lock Pose")
        btn_zero.setObjectName("btn_play")
        btn_zero.setToolTip("Adopt the tracker's CURRENT pose as the UI coordinate "
                            "frame.\nModel snaps to home; everything then moves "
                            "relative to this locked frame.")
        btn_zero.clicked.connect(self._calibrate_zero)
        btn_clear = QPushButton("Unlock")
        btn_clear.setMaximumWidth(96)
        btn_clear.setToolTip("Release the lock (back to the default room view).")
        btn_clear.clicked.connect(self._calibrate_clear)
        row.addWidget(btn_zero, 1)
        row.addWidget(btn_clear, 0)
        v.addLayout(row)

        self._calib_state = QLabel("Frame: default (not locked)")
        self._calib_state.setObjectName("hint")
        v.addWidget(self._calib_state)

        lbl = QLabel("Model alignment — rotate the CAD to match the real tracker:")
        lbl.setObjectName("hint")
        lbl.setWordWrap(True)
        v.addWidget(lbl)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        self._align_spins: dict[str, QSpinBox] = {}
        euler = CONFIG.calibration.model_offset_euler
        for i, (name, val) in enumerate(zip(("Roll", "Pitch", "Yaw"), euler)):
            grid.addWidget(QLabel(name), 0, i)
            sb = QSpinBox()
            sb.setRange(-180, 180)
            sb.setSingleStep(5)
            sb.setWrapping(True)
            sb.setSuffix("°")
            sb.setMaximumWidth(78)
            sb.blockSignals(True)
            sb.setValue(int(val))
            sb.blockSignals(False)
            sb.valueChanged.connect(self._update_model_alignment)
            grid.addWidget(sb, 1, i)
            self._align_spins[name] = sb
        v.addLayout(grid)

        row2 = QHBoxLayout()
        for label, axis in (("+90 X", "Roll"), ("+90 Y", "Pitch"), ("+90 Z", "Yaw")):
            b = QPushButton(label)
            b.setToolTip(f"Add 90° to {axis} — quick way to snap the model.")
            b.clicked.connect(lambda _=False, a=axis: self._nudge_alignment(a, 90))
            row2.addWidget(b)
        v.addLayout(row2)
        return g

    def _build_center_column(self) -> QWidget:
        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        # The 3D workspace dominates the window; the playback transport is a
        # compact strip below it.
        vsplit = QSplitter(Qt.Orientation.Vertical)
        self.viewport = Viewport3D()
        vsplit.addWidget(self.viewport)
        self.playback_controls = PlaybackControls()
        vsplit.addWidget(self.playback_controls)
        vsplit.setStretchFactor(0, 1)
        vsplit.setStretchFactor(1, 0)
        vsplit.setSizes([760, 190])
        v.addWidget(vsplit)
        return col

    def _build_right_column(self) -> QScrollArea:
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(6, 0, 0, 0)
        v.setSpacing(8)

        self.table = WaypointTable(self.waypoints)
        self.table.setMinimumHeight(260)
        self.log_panel = EventLogPanel()
        self.log_panel.setMinimumHeight(160)

        v.addWidget(self.table, 3)
        v.addWidget(self.log_panel, 2)
        return self._scroll(inner, 420)

    # ══════════════════════════════════════════════════════════════
    #  Signal wiring
    # ══════════════════════════════════════════════════════════════
    def _wire_signals(self) -> None:
        self.status_msg.connect(self._sb.showMessage)
        self.logger.entry_added.connect(self.log_panel.append_entry)

        self.table.changed.connect(self._on_waypoints_changed)

        pc = self.playback_controls
        pc.play_clicked.connect(self._start_playback)
        pc.pause_clicked.connect(self._toggle_pause)
        pc.stop_clicked.connect(self._stop_playback)
        pc.replay_clicked.connect(self._replay)
        pc.speed_changed.connect(self.playback.set_speed)

        # Sync the CAD display offset from the calibration defaults.
        self.viewport.set_model_offset(self._vive.calibration.model_R)

    # ══════════════════════════════════════════════════════════════
    #  Timers
    # ══════════════════════════════════════════════════════════════
    def _start_timers(self) -> None:
        t = CONFIG.timers
        self._t_render = QTimer(self); self._t_render.timeout.connect(self._render_tick); self._t_render.start(t.render_ms)
        self._t_button = QTimer(self); self._t_button.timeout.connect(self._button_tick); self._t_button.start(t.button_ms)
        self._t_status = QTimer(self); self._t_status.timeout.connect(self._status_tick); self._t_status.start(t.status_ms)

    def _render_tick(self) -> None:
        connected = self._vive.is_connected() and self._tracker_ok
        if connected:
            pose = self._vive.get_pose()
            self.waypoints.push_trail(pose)
            self.pose_panel.update_pose(pose)
            self.viewport.update_tracker(pose, valid=True)
            self.viewport.update_trail(self.waypoints.trail_array())
        else:
            self.pose_panel.set_no_signal()
            self.viewport.update_tracker(None, valid=False)

        self._refresh_scene_geometry()
        self._advance_playback()

    def _refresh_scene_geometry(self) -> None:
        positions = self.waypoints.waypoint_positions()
        labels = [wp.name for wp in self.waypoints.waypoints]
        self.viewport.update_waypoints(positions, labels)
        self.viewport.update_path(self.waypoints.path_segments())

    def _button_tick(self) -> None:
        if not self._vive.is_connected():
            return
        ev = self._vive.poll_buttons()
        if ev.record:
            self._capture_waypoint(from_hardware=True)
        if ev.play:
            self._start_playback(from_hardware=True)

    def _status_tick(self) -> None:
        st = self._vive.get_status()
        self.status_panel.update_status(st)
        now_ok = st.tracker == DeviceState.OK

        # Announce the moment it starts tracking (transition into OK).
        if now_ok and not self._tracker_ok:
            self.logger.event("Tracker is tracking — ready to capture")
            self.status_msg.emit("Tracker tracking — ready (Pin 3 capture, Pin 4 play)")
        self._tracker_ok = now_ok

        if now_ok:
            self._reconnect_logged = False
            return
        # Not tracking yet — keep trying to recover, every tick, indefinitely.
        # try_reconnect() re-opens the SteamVR session if it dropped, else just
        # re-finds the tracker device. Log only once per outage (no spam).
        self._vive.try_reconnect()
        if not self._reconnect_logged:
            self.logger.warn("Tracker not tracking — waiting for base station + "
                             "line of sight (auto-retrying)…")
            self._reconnect_logged = True

    # ══════════════════════════════════════════════════════════════
    #  Tracker connection
    # ══════════════════════════════════════════════════════════════
    def _toggle_tracker(self) -> None:
        if self._vive.is_connected():
            self._disconnect_tracker()
        else:
            self._connect_tracker()

    def _connect_tracker(self) -> None:
        self.status_msg.emit("Connecting to VIVE Tracker via SteamVR…")
        ok, msg = self._vive.connect()
        if ok:
            self._reconnects = 0
            self._tracker_lbl.setText(msg)
            self._tracker_lbl.setStyleSheet(f"color:{CONFIG.palette.ok};")
            self._btn_conn_tracker.setText("Disconnect Tracker")
            self.logger.event("SteamVR connected · VIVE Tracker online")
            self.status_msg.emit("VIVE Tracker connected — Pin 3 capture, Pin 4 play")
        else:
            self._tracker_ok = False
            self._tracker_lbl.setText(msg)
            self._tracker_lbl.setStyleSheet(f"color:{CONFIG.palette.err};")
            self._btn_conn_tracker.setText("Connect Tracker")
            self.logger.error(f"VIVE connect failed: {msg}")
            self.status_msg.emit(f"Tracker not connected: {msg}")

    # ── calibration ─────────────────────────────────────────────
    def _calibrate_zero(self) -> None:
        if not (self._vive.is_connected() and self._tracker_ok):
            self._warn("No tracker signal — cannot calibrate")
            return
        self._vive.calibrate_zero()
        self._calib_state.setText("Frame: LOCKED to tracker")
        self._calib_state.setStyleSheet(f"color:{CONFIG.palette.ok};")
        self.logger.event("Frame locked — UI adopted the tracker's current pose")
        self.status_msg.emit("Calibrated — UI frame locked to the tracker")

    def _calibrate_clear(self) -> None:
        self._vive.clear_calibration()
        self._calib_state.setText("Frame: default (not locked)")
        self._calib_state.setStyleSheet(f"color:{CONFIG.palette.text_dim};")
        self.logger.info("Frame unlocked — back to the default view")
        self.status_msg.emit("Calibration released")

    def _update_model_alignment(self, *_args) -> None:
        r = self._align_spins["Roll"].value()
        p = self._align_spins["Pitch"].value()
        y = self._align_spins["Yaw"].value()
        self._vive.calibration.set_model_offset_euler(r, p, y)
        self.viewport.set_model_offset(self._vive.calibration.model_R)
        self.status_msg.emit(f"Model alignment: R{r}° P{p}° Y{y}°")

    def _nudge_alignment(self, axis: str, delta: int) -> None:
        sb = self._align_spins[axis]
        new = sb.value() + delta
        new = ((new + 180) % 360) - 180   # wrap to [-180, 180]
        sb.setValue(new)                  # triggers _update_model_alignment

    def _disconnect_tracker(self) -> None:
        self._vive.disconnect()
        self._tracker_ok = False
        self._tracker_lbl.setText("Not connected")
        self._tracker_lbl.setStyleSheet(f"color:{CONFIG.palette.text_dim};")
        self._btn_conn_tracker.setText("Connect Tracker")
        self.logger.info("VIVE Tracker disconnected")
        self.status_msg.emit("Tracker disconnected")

    # ══════════════════════════════════════════════════════════════
    #  Playback
    # ══════════════════════════════════════════════════════════════
    def _advance_playback(self) -> None:
        now = time.monotonic()
        dt = now - self._last_frame_t
        self._last_frame_t = now

        frame = self.playback.update(dt)
        state = self.playback.state
        self.playback_controls.set_state(state)

        if frame is not None and self.playback.is_active:
            wps = self.waypoints.waypoints
            name = wps[frame.target_index].name if frame.target_index < len(wps) else "—"
            self.playback_controls.set_frame(frame.pose, frame.target_index,
                                             name, frame.progress)
            self.viewport.set_ghost(frame.pose)
            if frame.target_index < len(wps):
                self.viewport.set_highlight(wps[frame.target_index].pose.position)
        else:
            self.viewport.set_ghost(None)
            self.viewport.set_highlight(None)

        if state == PlaybackState.FINISHED and self._prev_pb_state != PlaybackState.FINISHED:
            self.logger.event("Playback finished")
            self.status_msg.emit("Playback finished")
        self._prev_pb_state = state

    def _start_playback(self, *_args, from_hardware: bool = False) -> None:
        if self.waypoints.count < 2:
            self._warn("Need at least 2 waypoints to play a path")
            return
        if not self.playback.load(self.waypoints.waypoints):
            self._warn("Waypoints are coincident — nothing to play")
            return
        self.playback.play()
        src = "Pin 4" if from_hardware else "UI"
        self.logger.event(f"Playback started ({self.waypoints.count} waypoints) [{src}]")
        self.status_msg.emit("Playback started")

    def _toggle_pause(self) -> None:
        self.playback.toggle_pause()

    def _stop_playback(self) -> None:
        self.playback.stop()
        self.playback_controls.reset()
        self.viewport.set_ghost(None)
        self.viewport.set_highlight(None)
        self.logger.info("Playback stopped")

    def _replay(self) -> None:
        if self.waypoints.count < 2:
            self._warn("Need at least 2 waypoints to play a path")
            return
        if self.playback.load(self.waypoints.waypoints):
            self.playback.replay()
            self.logger.event("Playback restarted")

    # ══════════════════════════════════════════════════════════════
    #  Teaching actions
    # ══════════════════════════════════════════════════════════════
    def _capture_waypoint(self, *_args, from_hardware: bool = False) -> None:
        if not (self._vive.is_connected() and self._tracker_ok):
            self._warn("No tracker signal — cannot capture a waypoint")
            return
        pose = self._vive.get_pose()
        wp = self.waypoints.capture(pose)
        self.table.refresh()
        self._refresh_scene_geometry()
        self.viewport.flash_tracker()
        src = "Pin 3" if from_hardware else "UI"
        self.logger.event(
            f"Waypoint {wp.number} captured  "
            f"X:{pose.x*1000:+.1f} Y:{pose.y*1000:+.1f} Z:{pose.z*1000:+.1f} mm [{src}]")
        self.status_msg.emit(f"Captured {wp.name}")

    def _undo_last(self) -> None:
        if self.waypoints.delete_last():
            self.table.refresh()
            self._refresh_scene_geometry()
            self.logger.info("Removed last waypoint")

    def _on_waypoints_changed(self) -> None:
        self._refresh_scene_geometry()

    # ══════════════════════════════════════════════════════════════
    #  Scene CAD (workspace + tracker model)
    # ══════════════════════════════════════════════════════════════
    _CAD_FILTER = "CAD mesh (*.stl *.stp *.step)"

    def _load_workspace_cad(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load workspace CAD", "", self._CAD_FILTER)
        if not path:
            return
        try:
            self.viewport.load_workspace_cad(path)
            self.logger.event(f"Workspace CAD loaded → {path}")
            self.status_msg.emit(f"Workspace CAD loaded — {path}")
        except Exception as e:
            self._warn(f"Workspace CAD load failed: {e}")
            self.logger.error(f"Workspace CAD load failed: {e}")

    def _clear_workspace_cad(self) -> None:
        self.viewport.clear_workspace_cad()
        self.logger.info("Workspace CAD cleared")
        self.status_msg.emit("Workspace CAD cleared")

    def _load_tracker_cad(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load tracker CAD (replaces the VIVE model)", "",
            self._CAD_FILTER)
        if not path:
            return
        try:
            self.viewport.load_tracker_cad(path)
            self.viewport.set_model_offset(self._vive.calibration.model_R)
            self.logger.event(f"Tracker CAD replaced → {path}")
            self.status_msg.emit(f"Tracker CAD replaced — {path}")
        except Exception as e:
            self._warn(f"Tracker CAD load failed: {e}")
            self.logger.error(f"Tracker CAD load failed: {e}")

    def _reset_tracker_cad(self) -> None:
        self.viewport.reset_tracker_cad()
        self.viewport.set_model_offset(self._vive.calibration.model_R)
        self.logger.info("Tracker CAD reset to VIVE Tracker 3.0")
        self.status_msg.emit("Tracker CAD reset to VIVE Tracker 3.0")

    # ══════════════════════════════════════════════════════════════
    #  Session
    # ══════════════════════════════════════════════════════════════
    def _new_session(self) -> None:
        self._clear_session(confirm=True)

    def _clear_session(self, confirm: bool = True) -> None:
        if confirm and self.waypoints.count and QMessageBox.question(
                self, "Clear session", "Remove all waypoints and the motion trail?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.playback.stop()
        self.playback_controls.reset()
        self.waypoints.clear_all()
        self.table.refresh()
        self._refresh_scene_geometry()
        self.viewport.update_trail(self.waypoints.trail_array())
        self.viewport.set_ghost(None)
        self.viewport.set_highlight(None)
        self.logger.info("Session cleared")
        self.status_msg.emit("Session cleared")

    def _save_session(self) -> None:
        if self.waypoints.count == 0:
            self._warn("Nothing to save")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save session", "session.json", "JSON (*.json)")
        if path:
            self.session.save(path)
            self.logger.event(f"Session saved → {path}")
            self.status_msg.emit(f"Session saved → {path}")

    def _load_session(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load session", "", "JSON (*.json)")
        if not path:
            return
        try:
            n = self.session.load(path)
            self.table.refresh()
            self._refresh_scene_geometry()
            self.viewport.update_trail(self.waypoints.trail_array())
            self.logger.event(f"Loaded {n} waypoints from {path}")
            self.status_msg.emit(f"Loaded {n} waypoints")
        except Exception as e:
            self._warn(f"Load failed: {e}")
            self.logger.error(f"Load failed: {e}")

    def _export_csv(self) -> None:
        if self.waypoints.count == 0:
            self._warn("Nothing to export")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "waypoints.csv", "CSV (*.csv)")
        if path:
            self.session.export_csv(path)
            self.logger.event(f"Exported CSV → {path}")
            self.status_msg.emit(f"Exported CSV → {path}")

    def _export_json(self) -> None:
        if self.waypoints.count == 0:
            self._warn("Nothing to export")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON", "waypoints.json", "JSON (*.json)")
        if path:
            self.session.export_json(path)
            self.logger.event(f"Exported JSON → {path}")
            self.status_msg.emit(f"Exported JSON → {path}")

    # ══════════════════════════════════════════════════════════════
    #  Misc
    # ══════════════════════════════════════════════════════════════
    def _warn(self, msg: str) -> None:
        self.status_msg.emit(msg)
        self.logger.warn(msg)

    def _show_help(self) -> None:
        QMessageBox.information(
            self, "Controls & Shortcuts",
            "<b>Teaching (real VIVE Tracker)</b><br>"
            "Move the tracker in space; the live pose + 3D marker follow it.<br>"
            "Pin 3 / Grip — capture waypoint (the Point & Play button)<br>"
            "Pin 4 / Trigger — play the taught path<br><br>"
            "<b>Keyboard (convenience)</b><br>"
            "Space — capture waypoint · Enter — play path · Ctrl+Z — undo<br><br>"
            "<b>3D camera</b><br>"
            "Drag — orbit · Scroll — zoom · Right-drag — pan<br><br>"
            "<b>Two path types</b><br>"
            "Cyan = motion trail (how the hand moved)<br>"
            "White = waypoint path (straight robot trajectory)")

    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key.Key_Space:
            self._capture_waypoint()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._start_playback()
        elif k == Qt.Key.Key_Z and ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._undo_last()
        else:
            super().keyPressEvent(ev)

    def closeEvent(self, ev):
        for t in (getattr(self, "_t_render", None),
                  getattr(self, "_t_button", None),
                  getattr(self, "_t_status", None)):
            if t:
                t.stop()
        if self._vive.is_connected():
            self._vive.disconnect()
        self.logger.info("Application closing")
        ev.accept()
