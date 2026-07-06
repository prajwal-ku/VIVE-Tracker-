"""
RobotPanel — backend selection + connection + program actions.

Presents the two robot backends (Serial/G-code over COM, FAIRINO over TCP/IP) and
shows only the fields relevant to the chosen one. It is pure UI: it reads the
connection parameters into a `ConnectionParams` and emits intents; the main
window owns the actual `RobotInterface` instances and does the work off-thread.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QComboBox, QSpinBox, QLineEdit, QWidget,
)

from ..config import CONFIG
from ..robot.base import RobotBackend, ConnectionParams


class RobotPanel(QGroupBox):
    backend_changed = pyqtSignal(object)     # RobotBackend
    refresh_ports = pyqtSignal()
    connect_clicked = pyqtSignal()
    disconnect_clicked = pyqtSignal()
    send_clicked = pyqtSignal()
    preview_clicked = pyqtSignal()
    export_clicked = pyqtSignal()

    def __init__(self):
        super().__init__("Robot")
        rc = CONFIG.robot
        v = QVBoxLayout(self)
        v.setSpacing(6)

        # Backend selector
        brow = QHBoxLayout()
        brow.addWidget(QLabel("Backend:"))
        self._backend = QComboBox()
        for b in RobotBackend:
            self._backend.addItem(b.value, b)
        self._backend.currentIndexChanged.connect(self._on_backend)
        brow.addWidget(self._backend, 1)
        v.addLayout(brow)

        self._avail = QLabel("")
        self._avail.setObjectName("hint")
        self._avail.setWordWrap(True)
        v.addWidget(self._avail)

        # ── Serial fields ───────────────────────────────────────
        self._serial_box = QWidget()
        sg = QGridLayout(self._serial_box)
        sg.setContentsMargins(0, 0, 0, 0)
        self._port = QComboBox()
        btn_ref = QPushButton("⟳")
        btn_ref.setFixedWidth(34)
        btn_ref.clicked.connect(self.refresh_ports)
        self._baud = QComboBox()
        for b in rc.baud_choices:
            self._baud.addItem(str(b))
        self._baud.setCurrentText(str(rc.default_baud))
        self._feed = QSpinBox()
        self._feed.setRange(10, 10000)
        self._feed.setValue(rc.default_feed)
        self._feed.setSuffix(" mm/min")
        sg.addWidget(QLabel("Port:"), 0, 0)
        sg.addWidget(self._port, 0, 1)
        sg.addWidget(btn_ref, 0, 2)
        sg.addWidget(QLabel("Baud:"), 1, 0)
        sg.addWidget(self._baud, 1, 1, 1, 2)
        sg.addWidget(QLabel("Feed:"), 2, 0)
        sg.addWidget(self._feed, 2, 1, 1, 2)
        v.addWidget(self._serial_box)

        # ── FAIRINO fields ──────────────────────────────────────
        self._fairino_box = QWidget()
        fg = QGridLayout(self._fairino_box)
        fg.setContentsMargins(0, 0, 0, 0)
        self._ip = QLineEdit(rc.fairino_default_ip)
        self._vel = QSpinBox()
        self._vel.setRange(1, 100)
        self._vel.setValue(rc.default_linear_vel)
        self._vel.setSuffix(" %")
        self._tool = QSpinBox(); self._tool.setRange(0, 15); self._tool.setValue(rc.default_tool)
        self._user = QSpinBox(); self._user.setRange(0, 15); self._user.setValue(rc.default_workpiece)
        fg.addWidget(QLabel("Controller IP:"), 0, 0)
        fg.addWidget(self._ip, 0, 1, 1, 3)
        fg.addWidget(QLabel("Vel:"), 1, 0)
        fg.addWidget(self._vel, 1, 1)
        fg.addWidget(QLabel("Tool:"), 1, 2)
        fg.addWidget(self._tool, 1, 3)
        fg.addWidget(QLabel("User:"), 2, 0)
        fg.addWidget(self._user, 2, 1)
        v.addWidget(self._fairino_box)

        # ── Actions ─────────────────────────────────────────────
        self._btn_conn = QPushButton("Connect")
        self._btn_conn.clicked.connect(self._on_connect_toggle)
        v.addWidget(self._btn_conn)

        arow = QHBoxLayout()
        self._btn_preview = QPushButton("Preview")
        self._btn_send = QPushButton("Send to Robot")
        self._btn_send.setObjectName("btn_play")
        self._btn_preview.clicked.connect(self.preview_clicked)
        self._btn_send.clicked.connect(self.send_clicked)
        arow.addWidget(self._btn_preview)
        arow.addWidget(self._btn_send)
        v.addLayout(arow)

        self._btn_export = QPushButton("Export program to file")
        self._btn_export.clicked.connect(self.export_clicked)
        v.addWidget(self._btn_export)

        self._status = QLabel("Not connected")
        self._status.setObjectName("hint")
        self._status.setWordWrap(True)
        v.addWidget(self._status)

        self._connected = False
        self._on_backend()

    # ── state ────────────────────────────────────────────────────
    def current_backend(self) -> RobotBackend:
        return self._backend.currentData()

    def params(self) -> ConnectionParams:
        b = self.current_backend()
        if b == RobotBackend.SERIAL_GCODE:
            return ConnectionParams(
                port=self._port.currentText(),
                baud=int(self._baud.currentText()),
                speed=self._feed.value())
        return ConnectionParams(
            host=self._ip.text().strip(),
            tcp_port=CONFIG.robot.fairino_tcp_port,
            speed=self._vel.value(),
            tool=self._tool.value(),
            workpiece=self._user.value())

    def set_ports(self, ports: list[str]) -> None:
        self._port.clear()
        self._port.addItems(ports if ports else ["No ports found"])

    def set_availability(self, available: bool, reason: str) -> None:
        self._avail.setText(reason)
        color = CONFIG.palette.ok if available else CONFIG.palette.warn
        self._avail.setStyleSheet(f"color:{color};")
        self._btn_send.setEnabled(available)

    def set_connected(self, connected: bool, message: str) -> None:
        self._connected = connected
        self._btn_conn.setText("Disconnect" if connected else "Connect")
        self._status.setText(message)
        self._status.setStyleSheet(
            f"color:{CONFIG.palette.ok if connected else CONFIG.palette.text_dim};")

    def set_status(self, message: str) -> None:
        self._status.setText(message)

    # ── internal ─────────────────────────────────────────────────
    def _on_backend(self, *_) -> None:
        b = self.current_backend()
        is_serial = b == RobotBackend.SERIAL_GCODE
        self._serial_box.setVisible(is_serial)
        self._fairino_box.setVisible(not is_serial)
        self.backend_changed.emit(b)

    def _on_connect_toggle(self) -> None:
        if self._connected:
            self.disconnect_clicked.emit()
        else:
            self.connect_clicked.emit()
