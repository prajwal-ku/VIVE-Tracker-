"""
Robot Point & Play — application entry point.

A Point & Play robot-teaching system: move a VIVE Tracker (tracked through
SteamVR) in 3D space, press the physical Point & Play button to capture
waypoints, visualise and play the taught path, and stream it to an industrial
robot (FAIRINO over TCP/IP, or a G-code controller over a COM port).

Run:
    python main.py

The application is organised as the `robotplay` package; this file only bootstraps
Qt and shows the main window. See README.md for the full architecture.
"""

import sys

from PyQt6.QtWidgets import QApplication
import pyqtgraph as pg

from robotplay.ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    pg.setConfigOptions(antialias=True, useOpenGL=True)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
