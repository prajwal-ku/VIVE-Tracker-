"""
Central configuration for the whole application.

Everything that is a "knob" — colours, workspace size, refresh rates, hardware
button bitmasks, default robot connection parameters — lives here so the rest of
the code never hard-codes magic numbers. Grouped into small dataclasses so a
future settings dialog can bind to them directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ──────────────────────────────────────────────────────────────────────────────
#  Colour palette (industrial dark theme)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Palette:
    bg:        str = "#0d1117"
    panel:     str = "#161b22"
    border:    str = "#30363d"
    text:      str = "#c9d1d9"
    text_dim:  str = "#8b949e"
    accent:    str = "#58a6ff"
    ok:        str = "#3fb950"
    ok_dim:    str = "#238636"
    warn:      str = "#d29922"
    err:       str = "#f85149"
    mono_green: str = "#7ee787"

    # 3D scene colours as normalised RGBA tuples
    scene_bg:      str = "#0d1117"
    grid_rgba:     tuple = (0.20, 0.22, 0.28, 0.45)
    axis_x_rgba:   tuple = (1.00, 0.30, 0.30, 1.0)   # X — red
    axis_y_rgba:   tuple = (0.30, 1.00, 0.30, 1.0)   # Y — green
    axis_z_rgba:   tuple = (0.35, 0.55, 1.00, 1.0)   # Z — blue
    tracker_rgba:  tuple = (0.20, 1.00, 0.40, 1.0)   # live tracker — bright green
    trail_rgba:    tuple = (0.00, 0.85, 1.00, 0.55)  # freehand motion trail — cyan
    waypoint_rgba: tuple = (1.00, 0.72, 0.00, 1.0)   # marked waypoints — gold
    wp_path_rgba:  tuple = (0.90, 0.90, 0.95, 0.90)  # straight waypoint path — white
    playback_rgba: tuple = (1.00, 0.30, 0.75, 1.0)   # playback ghost — magenta
    highlight_rgba:tuple = (1.00, 1.00, 1.00, 1.0)   # highlighted current waypoint


# ──────────────────────────────────────────────────────────────────────────────
#  3D workspace / scene
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SceneConfig:
    workspace_size:   float = 3.0    # metres, full width of the ground grid
    grid_spacing:     float = 0.25   # metres between grid lines
    axis_length:      float = 1.5    # metres, length of world XYZ axes
    triad_length:     float = 0.12   # metres, length of the tracker orientation triad
    cam_distance:     float = 4.0
    cam_elevation:    float = 28.0
    cam_azimuth:      float = 45.0
    waypoint_size:    float = 18.0   # px marker size
    tracker_size:     float = 15.0
    workspace_limit:  float = 1.5    # metres, +/- clamp for the simulated tracker


# ──────────────────────────────────────────────────────────────────────────────
#  Motion capture / trail
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CaptureConfig:
    max_trail_points: int   = 800     # rolling freehand motion-trail length
    min_trail_dist:   float = 0.003   # metres, min move before adding a trail point
    button_debounce:  float = 0.30    # seconds, hardware button cooldown


# ──────────────────────────────────────────────────────────────────────────────
#  Timers (Hz → millisecond period)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TimerConfig:
    render_hz:   int = 60    # 3D view + live pose refresh
    button_hz:   int = 30    # hardware button polling
    status_hz:   int = 2     # connection-status polling

    @property
    def render_ms(self) -> int: return max(1, int(1000 / self.render_hz))
    @property
    def button_ms(self) -> int: return max(1, int(1000 / self.button_hz))
    @property
    def status_ms(self) -> int: return max(1, int(1000 / self.status_hz))


# ──────────────────────────────────────────────────────────────────────────────
#  Vive Tracker hardware buttons (pogo-pin bitmasks via OpenVR)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TrackerButtons:
    # Pin 3 / Grip → capture waypoint ("Point & Play" button)
    record_bitmask: int = (1 << 2)
    # Pin 4 / Trigger → start playback
    play_bitmask:   int = (1 << 33)


# ──────────────────────────────────────────────────────────────────────────────
#  Robot connection defaults
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RobotConfig:
    # Serial / G-code backend
    default_baud:     int = 115200
    baud_choices:     tuple = (9600, 19200, 38400, 57600, 115200, 250000)
    default_feed:     int = 1000     # mm/min for the G-code backend

    # FAIRINO TCP/IP backend (FAIRINO_SimMachine / real controller)
    fairino_default_ip: str = "192.168.58.2"
    fairino_tcp_port:   int = 8080
    default_linear_vel: int = 30      # % of max, MoveL velocity for FAIRINO
    default_tool:       int = 0
    default_workpiece:  int = 0


@dataclass(frozen=True)
class PlaybackConfig:
    default_speed:   float = 0.25    # metres / second along the waypoint path
    speed_min:       float = 0.02
    speed_max:       float = 2.0


@dataclass(frozen=True)
class AppConfig:
    """Top-level configuration aggregate — one instance shared by the app."""
    palette:  Palette        = field(default_factory=Palette)
    scene:    SceneConfig     = field(default_factory=SceneConfig)
    capture:  CaptureConfig   = field(default_factory=CaptureConfig)
    timers:   TimerConfig     = field(default_factory=TimerConfig)
    buttons:  TrackerButtons  = field(default_factory=TrackerButtons)
    robot:    RobotConfig     = field(default_factory=RobotConfig)
    playback: PlaybackConfig  = field(default_factory=PlaybackConfig)

    window_title: str = "Robot Point & Play  ·  VIVE Teaching System"
    window_size:  tuple = (1440, 900)


# A single shared instance imported across the app.
CONFIG = AppConfig()
