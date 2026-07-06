"""
WaypointTable — the professional waypoint grid with edit actions.

Columns: #, Name, Timestamp, X, Y, Z, Roll, Pitch, Yaw. The Name column is
editable in place (rename); toolbar buttons delete, reorder (up/down) and clear.
The widget owns no data — it reflects a `WaypointManager` and emits `changed`
whenever it mutates it, so the main window can refresh the 3D view and program
preview from one place.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QAbstractItemView, QSizePolicy,
)

from ..config import CONFIG
from ..core.waypoint_manager import WaypointManager


class WaypointTable(QGroupBox):
    changed = pyqtSignal()   # emitted whenever the underlying data changes

    _HEADERS = ["#", "Name", "Timestamp", "X (mm)", "Y (mm)", "Z (mm)",
                "Roll°", "Pitch°", "Yaw°"]

    def __init__(self, manager: WaypointManager):
        super().__init__("Waypoints")
        self._wm = manager
        self._loading = False

        v = QVBoxLayout(self)

        self._table = QTableWidget(0, len(self._HEADERS))
        self._table.setHorizontalHeaderLabels(self._HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked)
        # Size every column to its contents and let the table scroll
        # horizontally — nine columns never fit a narrow panel without either
        # truncation or scrolling, and showing full values beats truncating them.
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        self._table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel)
        # Let the table shrink with a narrow panel (it scrolls horizontally)
        # instead of forcing the whole column wider.
        self._table.setSizePolicy(QSizePolicy.Policy.Ignored,
                                  QSizePolicy.Policy.Expanding)
        self._table.itemChanged.connect(self._on_item_changed)
        v.addWidget(self._table)

        row = QHBoxLayout()
        self._btn_up = QPushButton("↑ Up")
        self._btn_down = QPushButton("↓ Down")
        self._btn_del = QPushButton("Delete")
        self._btn_del.setObjectName("btn_danger")
        self._count = QLabel("0 waypoints")
        self._count.setObjectName("hint")
        self._btn_up.clicked.connect(lambda: self._reorder(-1))
        self._btn_down.clicked.connect(lambda: self._reorder(+1))
        self._btn_del.clicked.connect(self._delete_selected)
        row.addWidget(self._btn_up)
        row.addWidget(self._btn_down)
        row.addWidget(self._btn_del)
        row.addStretch()
        row.addWidget(self._count)
        v.addLayout(row)

    # ── refresh from manager ────────────────────────────────────
    def refresh(self) -> None:
        self._loading = True
        wps = self._wm.waypoints
        self._table.setRowCount(len(wps))
        for r, wp in enumerate(wps):
            p = wp.pose
            # Show time-only (the date is redundant within a session).
            ts = wp.timestamp.split("T")[-1] if "T" in wp.timestamp else wp.timestamp
            values = [
                str(wp.number), wp.name, ts,
                f"{p.x*1000:+.1f}", f"{p.y*1000:+.1f}", f"{p.z*1000:+.1f}",
                f"{p.roll:+.1f}", f"{p.pitch:+.1f}", f"{p.yaw:+.1f}",
            ]
            for c, text in enumerate(values):
                item = QTableWidgetItem(text)
                if c == 1:   # Name column is editable
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    item.setForeground(QColor(CONFIG.palette.mono_green))
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c >= 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(r, c, item)
        self._count.setText(f"{len(wps)} waypoint{'s' if len(wps) != 1 else ''}")
        self._loading = False

    # ── selection helpers ───────────────────────────────────────
    def selected_row(self) -> int:
        rows = self._table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def select_row(self, index: int) -> None:
        if 0 <= index < self._table.rowCount():
            self._table.selectRow(index)

    # ── edit actions ────────────────────────────────────────────
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != 1:
            return
        name = item.text().strip()
        if name and self._wm.rename(item.row(), name):
            self.changed.emit()

    def _delete_selected(self) -> None:
        r = self.selected_row()
        if r < 0:
            return
        if self._wm.delete(r):
            self.refresh()
            self.changed.emit()

    def _reorder(self, direction: int) -> None:
        r = self.selected_row()
        if r < 0:
            return
        new = r + direction
        if self._wm.move(r, new):
            self.refresh()
            self.select_row(new)
            self.changed.emit()
