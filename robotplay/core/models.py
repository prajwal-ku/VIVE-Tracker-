"""
Data models and orientation maths.

`TrackerData` is the single 6DoF pose type that flows through the whole app —
trackers produce it, the 3D view renders it, waypoints store it, the robot
drivers consume it. Orientation is carried both as a quaternion (canonical, used
for interpolation) and as roll/pitch/yaw Euler angles in degrees (for display).

The quaternion helpers are deliberately dependency-light (numpy only) so this
module has no Qt / hardware coupling and is trivially unit-testable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np


# ──────────────────────────────────────────────────────────────────────────────
#  Quaternion / Euler / matrix conversions   (quaternion order: w, x, y, z)
# ──────────────────────────────────────────────────────────────────────────────

def quat_normalize(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=float)
    n = np.linalg.norm(q)
    if n < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0])
    return q / n


def quat_from_matrix(R: np.ndarray) -> np.ndarray:
    """Rotation matrix (3x3) → quaternion (w, x, y, z)."""
    R = np.asarray(R, dtype=float)
    t = np.trace(R)
    if t > 0.0:
        s = math.sqrt(t + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return quat_normalize(np.array([w, x, y, z]))


def quat_to_matrix(q: np.ndarray) -> np.ndarray:
    """Quaternion (w, x, y, z) → 3x3 rotation matrix."""
    w, x, y, z = quat_normalize(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w),     2 * (x * z + y * w)],
        [2 * (x * y + z * w),     1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w),     2 * (y * z + x * w),     1 - 2 * (x * x + y * y)],
    ])


def quat_to_euler(q: np.ndarray) -> tuple[float, float, float]:
    """Quaternion → (roll, pitch, yaw) in DEGREES (aerospace ZYX / Tait-Bryan)."""
    w, x, y, z = quat_normalize(q)

    sinr_cosp = 2 * (w * x + y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.asin(sinp)

    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def euler_to_quat(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """(roll, pitch, yaw) in DEGREES → quaternion (w, x, y, z)."""
    r, p, yw = map(math.radians, (roll, pitch, yaw))
    cr, sr = math.cos(r / 2), math.sin(r / 2)
    cp, sp = math.cos(p / 2), math.sin(p / 2)
    cy, sy = math.cos(yw / 2), math.sin(yw / 2)
    return quat_normalize(np.array([
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ]))


def quat_slerp(q0: np.ndarray, q1: np.ndarray, t: float) -> np.ndarray:
    """Spherical linear interpolation between two quaternions."""
    q0 = quat_normalize(q0)
    q1 = quat_normalize(q1)
    dot = float(np.dot(q0, q1))
    if dot < 0.0:            # take the shortest arc
        q1 = -q1
        dot = -dot
    if dot > 0.9995:        # nearly identical — fall back to linear
        return quat_normalize(q0 + t * (q1 - q0))
    theta0 = math.acos(max(-1.0, min(1.0, dot)))
    theta = theta0 * t
    q2 = quat_normalize(q1 - q0 * dot)
    return q0 * math.cos(theta) + q2 * math.sin(theta)


# ──────────────────────────────────────────────────────────────────────────────
#  TrackerData — one 6DoF pose
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TrackerData:
    """A single 6DoF pose. Position in metres, orientation as roll/pitch/yaw
    (degrees) plus the equivalent quaternion (w, x, y, z)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll:  float = 0.0
    pitch: float = 0.0
    yaw:   float = 0.0
    qw: float = 1.0
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0

    # ── constructors ─────────────────────────────────────────────
    @classmethod
    def from_matrix(cls, x: float, y: float, z: float, R: np.ndarray) -> "TrackerData":
        q = quat_from_matrix(R)
        roll, pitch, yaw = quat_to_euler(q)
        return cls(x, y, z, roll, pitch, yaw, *q)

    @classmethod
    def from_euler(cls, x, y, z, roll, pitch, yaw) -> "TrackerData":
        q = euler_to_quat(roll, pitch, yaw)
        return cls(x, y, z, roll, pitch, yaw, *q)

    # ── accessors ────────────────────────────────────────────────
    @property
    def position(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], dtype=float)

    @property
    def quaternion(self) -> np.ndarray:
        return np.array([self.qw, self.qx, self.qy, self.qz], dtype=float)

    @property
    def rotation_matrix(self) -> np.ndarray:
        return quat_to_matrix(self.quaternion)

    def copy(self) -> "TrackerData":
        return TrackerData(self.x, self.y, self.z, self.roll, self.pitch,
                           self.yaw, self.qw, self.qx, self.qy, self.qz)

    # ── serialisation ────────────────────────────────────────────
    def as_dict(self) -> dict:
        return dict(x=self.x, y=self.y, z=self.z,
                    roll=self.roll, pitch=self.pitch, yaw=self.yaw,
                    qw=self.qw, qx=self.qx, qy=self.qy, qz=self.qz)

    @classmethod
    def from_dict(cls, d: dict) -> "TrackerData":
        # Backward-compatible with older sessions that stored only x/y/z + euler.
        if "qw" not in d:
            return cls.from_euler(d.get("x", 0), d.get("y", 0), d.get("z", 0),
                                  d.get("roll", 0), d.get("pitch", 0), d.get("yaw", 0))
        return cls(**{k: d[k] for k in
                      ("x", "y", "z", "roll", "pitch", "yaw",
                       "qw", "qx", "qy", "qz") if k in d})


def interpolate_pose(a: TrackerData, b: TrackerData, t: float) -> TrackerData:
    """Linear position + slerp orientation between two poses (0 ≤ t ≤ 1)."""
    t = max(0.0, min(1.0, t))
    pos = a.position + t * (b.position - a.position)
    q = quat_slerp(a.quaternion, b.quaternion, t)
    roll, pitch, yaw = quat_to_euler(q)
    return TrackerData(pos[0], pos[1], pos[2], roll, pitch, yaw, *q)


# ──────────────────────────────────────────────────────────────────────────────
#  Waypoint — a captured, labelled pose
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Waypoint:
    """A pose captured by the operator, annotated with a number, name and time."""

    number: int
    pose: TrackerData
    name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def __post_init__(self):
        if not self.name:
            self.name = f"P{self.number:02d}"

    def as_dict(self) -> dict:
        return dict(number=self.number, name=self.name,
                    timestamp=self.timestamp, pose=self.pose.as_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "Waypoint":
        return cls(number=d["number"],
                   pose=TrackerData.from_dict(d["pose"]),
                   name=d.get("name", ""),
                   timestamp=d.get("timestamp",
                                   datetime.now().isoformat(timespec="seconds")))
