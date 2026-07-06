"""
MainWindow — assembles every module into the application.

Runs on a real HTC VIVE Tracker (SteamVR/OpenVR) only — there is no simulated
pose source. On start it attempts to connect; the connection-status board and
live-pose panel reflect the true hardware state (nothing shows "OK" unless the
tracker is really tracking).

Responsibilities (kept thin; the real work lives in the modules):
    • own the shared services (logger, waypoint/session/playback managers)
    • own the VIVE tracker driver and its connection lifecycle
    • own the robot drivers (serial / FAIRINO) and run programs off-thread
    • drive three timers: render (pose + 3D + playback), hardware buttons, status
    • translate UI intents into calls on the managers, and refresh the views

The side columns live in scroll areas so a small screen scrolls instead of
overlapping, while a large monitor lays everything out neatly.
"""

from __future__ import annotations

import threading
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget,
    QGroupBox, QPushButton, QLabel, QTextEdit, QScrollArea, QFrame,
    QFileDialog, QMessageBox, QStatusBar, QSizePolicy,
)

from ..config import CONFIG
from ..core.logger import EventLogger
from ..core.waypoint_manager import WaypointManager
from ..core.session_manager import SessionManager
from ..core.playback_engine import PlaybackEngine, PlaybackState
from ..tracker import ViveTracker, DeviceState
from ..robot import BACKENDS
from ..robot.base import RobotBackend
from .style import build_stylesheet
from .viewport import Viewport3D
from .panels import ConnectionStatusPanel, LivePosePanel, EventLogPanel
from .waypoint_table import WaypointTable
from .playback_controls import PlaybackControls
from .robot_panel import RobotPanel


class MainWindow(QMainWindow):
    # Cross-thread signals (robot worker → GUI thread).
    status_msg = pyqtSignal(str)
    robot_msg = pyqtSignal(str)

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

        # ── robots ──────────────────────────────────────────────
        self._robots = {b: cls() for b, cls in BACKENDS.items()}
        self._robot = self._robots[RobotBackend.SERIAL_GCODE]

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
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([348, 700, 484])

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
        self.status_panel = ConnectionStatusPanel()
        v.addWidget(self.status_panel)
        self.pose_panel = LivePosePanel()
        v.addWidget(self.pose_panel)
        v.addWidget(self._build_controls_group())
        v.addStretch()
        return self._scroll(inner, 348)

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

    def _build_controls_group(self) -> QGroupBox:
        g = QGroupBox("Teaching Controls")
        v = QVBoxLayout(g)
        v.setSpacing(6)

        self._btn_capture = QPushButton("●  CAPTURE WAYPOINT")
        self._btn_capture.setObjectName("btn_record")
        self._btn_capture.setToolTip(
            "Capture the current tracker pose as a waypoint.  [Space]\n"
            "Hardware: Pin 3 / Grip (the Point & Play button).")
        self._btn_capture.clicked.connect(self._capture_waypoint)
        v.addWidget(self._btn_capture)

        self._btn_teach_play = QPushButton("▶  PLAY PATH")
        self._btn_teach_play.setObjectName("btn_play")
        self._btn_teach_play.setToolTip(
            "Animate a virtual tracker along the waypoint path.  [Enter]\n"
            "Hardware: Pin 4 / Trigger.")
        self._btn_teach_play.clicked.connect(self._start_playback)
        v.addWidget(self._btn_teach_play)

        # Let the wide buttons shrink with the column instead of forcing its width.
        for b in (self._btn_capture, self._btn_teach_play):
            b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout()
        b_undo = QPushButton("Undo last")
        b_undo.clicked.connect(self._undo_last)
        b_clear = QPushButton("Clear all")
        b_clear.setObjectName("btn_danger")
        b_clear.clicked.connect(self._clear_session)
        row.addWidget(b_undo)
        row.addWidget(b_clear)
        v.addLayout(row)

        self._pin_hint = QLabel("Pin 3 (Grip) = Capture  •  Pin 4 (Trigger) = Play")
        self._pin_hint.setObjectName("hint")
        self._pin_hint.setWordWrap(True)
        v.addWidget(self._pin_hint)
        return g

    def _build_center_column(self) -> QWidget:
        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        vsplit = QSplitter(Qt.Orientation.Vertical)

        self._tabs = QTabWidget()
        self.viewport = Viewport3D()
        self._tabs.addTab(self.viewport, "3D Workspace")
        self._program_view = QTextEdit()
        self._program_view.setReadOnly(True)
        self._program_view.setPlaceholderText(
            "Capture waypoints, then Preview / Send — the robot program appears here.")
        self._tabs.addTab(self._program_view, "Program Preview")
        vsplit.addWidget(self._tabs)

        self.playback_controls = PlaybackControls()
        vsplit.addWidget(self.playback_controls)
        vsplit.setStretchFactor(0, 1)
        vsplit.setStretchFactor(1, 0)
        vsplit.setSizes([560, 210])
        v.addWidget(vsplit)
        return col

    def _build_right_column(self) -> QScrollArea:
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(6, 0, 0, 0)
        v.setSpacing(8)

        self.table = WaypointTable(self.waypoints)
        self.table.setMinimumHeight(240)
        self.robot_panel = RobotPanel()
        self.log_panel = EventLogPanel()
        self.log_panel.setMinimumHeight(160)

        v.addWidget(self.table, 3)
        v.addWidget(self.robot_panel, 0)
        v.addWidget(self.log_panel, 2)
        return self._scroll(inner, 484)

    # ══════════════════════════════════════════════════════════════
    #  Signal wiring
    # ══════════════════════════════════════════════════════════════
    def _wire_signals(self) -> None:
        self.status_msg.connect(self._sb.showMessage)
        self.robot_msg.connect(self.robot_panel.set_status)
        self.logger.entry_added.connect(self.log_panel.append_entry)

        self.table.changed.connect(self._on_waypoints_changed)

        pc = self.playback_controls
        pc.play_clicked.connect(self._start_playback)
        pc.pause_clicked.connect(self._toggle_pause)
        pc.stop_clicked.connect(self._stop_playback)
        pc.replay_clicked.connect(self._replay)
        pc.speed_changed.connect(self.playback.set_speed)

        rp = self.robot_panel
        rp.backend_changed.connect(self._on_backend_changed)
        rp.refresh_ports.connect(self._refresh_ports)
        rp.connect_clicked.connect(self._connect_robot)
        rp.disconnect_clicked.connect(self._disconnect_robot)
        rp.preview_clicked.connect(self._preview_program)
        rp.send_clicked.connect(self._send_program)
        rp.export_clicked.connect(self._export_program)

        # Initialise robot panel state for the default backend.
        self._on_backend_changed(RobotBackend.SERIAL_GCODE)

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
        self._tracker_ok = st.tracker == DeviceState.OK

        if not self._vive.is_connected():
            return
        # Auto-reconnect the VIVE tracker if the signal drops.
        if st.tracker in (DeviceState.ERROR, DeviceState.WARN):
            if self._reconnects < 5:
                self._reconnects += 1
                self.logger.warn(
                    f"Tracker signal issue — reconnecting ({self._reconnects}/5)")
                self._vive.try_reconnect()
        else:
            self._reconnects = 0

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
        self._refresh_program_if_open()
        src = "Pin 3" if from_hardware else "UI"
        self.logger.event(
            f"Waypoint {wp.number} captured  "
            f"X:{pose.x*1000:+.1f} Y:{pose.y*1000:+.1f} Z:{pose.z*1000:+.1f} mm [{src}]")
        self.status_msg.emit(f"Captured {wp.name}")

    def _undo_last(self) -> None:
        if self.waypoints.delete_last():
            self.table.refresh()
            self._refresh_scene_geometry()
            self._refresh_program_if_open()
            self.logger.info("Removed last waypoint")

    def _on_waypoints_changed(self) -> None:
        self._refresh_scene_geometry()
        self._refresh_program_if_open()

    # ══════════════════════════════════════════════════════════════
    #  Robot
    # ══════════════════════════════════════════════════════════════
    def _on_backend_changed(self, backend: RobotBackend) -> None:
        self._robot = self._robots[backend]
        available, reason = self._robot.is_available()
        self.robot_panel.set_availability(available, reason)
        self.robot_panel.set_connected(self._robot.is_connected(),
                                       "Connected" if self._robot.is_connected()
                                       else "Not connected")
        if backend == RobotBackend.SERIAL_GCODE:
            self._refresh_ports()
        self.logger.info(f"Robot backend: {backend.value}")

    def _refresh_ports(self) -> None:
        self.robot_panel.set_ports(self._robot.list_ports())

    def _connect_robot(self) -> None:
        params = self.robot_panel.params()
        ok, msg = self._robot.connect(params)
        self.robot_panel.set_connected(ok, msg)
        (self.logger.event if ok else self.logger.error)(f"Robot: {msg}")
        self.status_msg.emit(msg)

    def _disconnect_robot(self) -> None:
        self._robot.disconnect()
        self.robot_panel.set_connected(False, "Disconnected")
        self.logger.info("Robot disconnected")

    def _preview_program(self) -> None:
        if self.waypoints.count == 0:
            self._warn("No waypoints to preview")
            return
        text = self._robot.preview_program(self.waypoints.waypoints,
                                            self.robot_panel.params())
        self._program_view.setPlainText(text)
        self._tabs.setCurrentIndex(1)
        self.logger.info("Generated program preview")

    def _refresh_program_if_open(self) -> None:
        if self._tabs.currentIndex() == 1 and self.waypoints.count:
            self._program_view.setPlainText(
                self._robot.preview_program(self.waypoints.waypoints,
                                            self.robot_panel.params()))

    def _send_program(self) -> None:
        if not self._robot.is_connected():
            self._warn("Connect to the robot first")
            return
        if self.waypoints.count == 0:
            self._warn("No waypoints to send")
            return
        params = self.robot_panel.params()
        wps = list(self.waypoints.waypoints)
        self.logger.event(f"Sending {len(wps)} waypoints to robot…")

        def worker():
            ok, msg = self._robot.send_program(
                wps, params,
                progress=lambda i, t, m: self.robot_msg.emit(m))
            self.robot_msg.emit(msg)
            self.status_msg.emit(msg)

        threading.Thread(target=worker, daemon=True).start()

    def _export_program(self) -> None:
        if self.waypoints.count == 0:
            self._warn("No waypoints to export")
            return
        is_serial = self._robot.backend == RobotBackend.SERIAL_GCODE
        default = "robot_path.gcode" if is_serial else "fairino_program.py"
        flt = "G-code (*.gcode *.nc *.txt)" if is_serial else "Python (*.py)"
        path, _ = QFileDialog.getSaveFileName(self, "Export program", default, flt)
        if not path:
            return
        text = self._robot.preview_program(self.waypoints.waypoints,
                                            self.robot_panel.params())
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self.logger.event(f"Program exported → {path}")
        self.status_msg.emit(f"Program exported → {path}")

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
        self._program_view.clear()
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
        for robot in self._robots.values():
            if robot.is_connected():
                robot.disconnect()
        self.logger.info("Application closing")
        ev.accept()
