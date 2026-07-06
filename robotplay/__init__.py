"""
Robot Point & Play — a Point & Play robot teaching system.

An operator moves a VIVE Tracker (tracked through SteamVR) in 3D space. A
physical "Point & Play" button captures the current 6DoF pose as a waypoint.
The application visualises the live motion, records waypoints, plays the taught
path back, and streams the resulting trajectory to an industrial robot
(FAIRINO over TCP/IP, or any G-code controller over a COM port).

The package is organised into loosely-coupled layers so it can grow towards a
full digital-twin / ROS2 / MoveIt integration without rewrites:

    robotplay.config              global configuration / theme constants
    robotplay.core                data models, logger, managers, playback
    robotplay.tracker             TrackerInterface abstraction + drivers
    robotplay.robot               RobotInterface abstraction + drivers
    robotplay.ui                  PyQt6 widgets and the main window
"""

__version__ = "3.0.0"
__all__ = ["__version__"]
