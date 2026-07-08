"""
TrackerModel — a CAD-like 3D VIVE Tracker that follows the live pose.

Instead of drawing the tracker as a dot, this builds a recognisable VIVE Tracker
puck out of OpenGL mesh primitives (a tapered disc body, a recessed sensor face,
the ¼-20 mount stub, a status LED and a forward pointer that shows heading) and
rigidly transforms the whole assembly by the tracker's 6DoF pose every frame — so
moving/rotating the real tracker moves/rotates the on-screen model in real time.

If you have a real CAD file, set `CONFIG.scene.tracker_stl_path` to a `.stl`; it
is loaded (binary or ASCII, no extra dependencies), recentred and scaled to fit,
and used instead of the procedural model. The procedural model is the always-works
fallback.

Each part is created once in the model's local frame with a fixed *base*
transform; every frame we set each part's transform to `pose · base`, which is a
single matrix multiply per part — cheap enough for 60 Hz.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph.opengl as gl
from pyqtgraph import Transform3D
from pyqtgraph.opengl.shaders import ShaderProgram, VertexShader, FragmentShader

from ..config import CONFIG
from .mesh_loader import load_mesh


# A brighter version of pyqtgraph 0.14's modern "shaded" shader (same
# u_mvp/u_normal uniforms + a_position/a_normal/a_color attributes). High ambient
# (0.5) with two-sided diffuse (abs of the light dot) so the CAD stays clearly
# lit from every angle — the stock shader drops shadowed/concave faces to
# 0.2·colour, which reads as black on the dark workspace and hides the model.
_BRIGHT_SHADER = ShaderProgram("brightShaded", [
    VertexShader("""
        uniform mat4 u_mvp;
        uniform mat3 u_normal;
        attribute vec4 a_position;
        attribute vec3 a_normal;
        attribute vec4 a_color;
        varying vec4 v_color;
        varying vec3 v_normal;
        void main() {
            v_normal = normalize(u_normal * a_normal);
            v_color = a_color;
            gl_Position = u_mvp * a_position;
        }
    """),
    FragmentShader("""
        #ifdef GL_ES
        precision mediump float;
        #endif
        varying vec4 v_color;
        varying vec3 v_normal;
        void main() {
            float p = abs(dot(v_normal, normalize(vec3(0.3, -0.5, 1.0))));
            vec3 rgb = v_color.rgb * (0.5 + 0.5 * p);
            gl_FragColor = vec4(rgb, v_color.a);
        }
    """),
])


def _fit_mesh(verts: np.ndarray, target: float) -> np.ndarray:
    """Recentre to the origin and scale so the largest extent equals `target`."""
    centre = (verts.max(axis=0) + verts.min(axis=0)) / 2.0
    verts = verts - centre
    extent = float(np.abs(verts).max()) * 2.0
    if extent > 1e-9:
        verts = verts * (target / extent)
    return verts


# ──────────────────────────────────────────────────────────────────────────────
#  Tracker model
# ──────────────────────────────────────────────────────────────────────────────

class TrackerModel:
    def __init__(self, view: gl.GLViewWidget,
                 body=(0.80, 0.84, 0.92, 1.0),
                 accent=(0.20, 1.00, 0.45, 1.0),
                 ghost: bool = False,
                 mesh_path: str | None = None):
        self._view = view
        self._ghost = ghost
        self._parts: list[tuple[gl.GLGraphicsItem, Transform3D]] = []
        self._body_items: list[gl.GLMeshItem] = []
        self._body_color = body

        # Priority: an explicit mesh (user "Load Tracker CAD"), else the config
        # override, else the bundled real VIVE Tracker 3.0 CAD, else procedural.
        source = mesh_path or CONFIG.scene.tracker_stl_path or self._bundled_asset()
        if source:
            try:
                self._build_from_mesh(source, body)
            except Exception:
                self._build_procedural(body, accent)
        else:
            self._build_procedural(body, accent)

        self.set_visible(not ghost)  # ghost starts hidden

    def remove(self) -> None:
        """Remove every mesh item of this model from the view."""
        for item, _ in self._parts:
            self._view.removeItem(item)
        self._parts.clear()
        self._body_items.clear()

    @staticmethod
    def _bundled_asset() -> str:
        """Path to the packaged VIVE Tracker CAD mesh, if present."""
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "assets",
                            "vive_tracker.stl")
        path = os.path.abspath(path)
        return path if os.path.isfile(path) else ""

    # ── geometry helpers ────────────────────────────────────────
    def _add(self, meshdata: gl.MeshData, color, base: Transform3D,
             is_body: bool = False) -> gl.GLMeshItem:
        # Ghosts render as a solid distinct colour (translucency on a dense CAD
        # mesh has no depth sorting → visible artifacts), so keep everything
        # opaque and distinguish the playback ghost by colour instead.
        item = gl.GLMeshItem(meshdata=meshdata, color=color, shader=_BRIGHT_SHADER,
                             smooth=True, drawEdges=False, glOptions="opaque")
        self._view.addItem(item)
        self._parts.append((item, base))
        if is_body:
            self._body_items.append(item)
        return item

    @staticmethod
    def _cyl(r0: float, r1: float, length: float, cols: int = 40) -> gl.MeshData:
        return gl.MeshData.cylinder(rows=1, cols=cols,
                                    radius=[r0, r1], length=length)

    @staticmethod
    def _xform(tx=0.0, ty=0.0, tz=0.0, angle=0.0, ax=0.0, ay=0.0, az=1.0) -> Transform3D:
        t = Transform3D()
        t.translate(tx, ty, tz)
        if angle:
            t.rotate(angle, ax, ay, az)
        return t

    # ── procedural VIVE tracker ─────────────────────────────────
    def _build_procedural(self, body, accent) -> None:
        s = CONFIG.scene.tracker_model_scale
        dark = (0.16, 0.17, 0.21, 1.0)
        mid = body

        # Body puck — tapered disc (wider at the bottom, like the real tracker).
        r_top, r_bot, h = 0.052 * s, 0.060 * s, 0.030 * s
        self._add(self._cyl(r_bot, r_top, h), mid,
                  self._xform(tz=-h / 2), is_body=True)

        # Recessed sensor face on top (slightly inset darker disc).
        self._add(self._cyl(0.050 * s, 0.044 * s, 0.006 * s), dark,
                  self._xform(tz=h / 2), is_body=True)

        # ¼-20 mount stub underneath.
        self._add(self._cyl(0.013 * s, 0.013 * s, 0.016 * s), dark,
                  self._xform(tz=-h / 2 - 0.016 * s), is_body=True)

        # Forward pointer/tip (shows heading, gives the "pen" feel) — accent cone.
        tip_len = 0.070 * s
        self._add(self._cyl(0.016 * s, 0.0, tip_len), accent,
                  self._xform(tx=r_bot, angle=90, ay=1.0))  # cone points +X

        # Status LED at the front face.
        led = gl.MeshData.sphere(rows=10, cols=16, radius=0.010 * s)
        self._add(led, (1.0, 0.35, 0.30, 1.0),
                  self._xform(tx=r_top * 0.9, tz=h * 0.35))

    # ── STL-based model ─────────────────────────────────────────
    def _build_from_mesh(self, path: str, color) -> None:
        verts, faces = load_mesh(path)
        verts = _fit_mesh(verts, CONFIG.scene.tracker_model_size)
        md = gl.MeshData(vertexes=verts, faces=faces)
        self._add(md, color, Transform3D(), is_body=True)

    # ── per-frame update ────────────────────────────────────────
    def set_pose(self, position: np.ndarray, R: np.ndarray) -> None:
        pose = Transform3D(
            R[0, 0], R[0, 1], R[0, 2], position[0],
            R[1, 0], R[1, 1], R[1, 2], position[1],
            R[2, 0], R[2, 1], R[2, 2], position[2],
            0.0, 0.0, 0.0, 1.0,
        )
        for item, base in self._parts:
            item.setTransform(pose * base)

    def set_visible(self, visible: bool) -> None:
        for item, _ in self._parts:
            item.setVisible(visible)

    def flash(self, color=(1.0, 0.82, 0.0, 1.0), ms: int = 180) -> None:
        """Briefly tint the body (used when a waypoint is captured)."""
        from PyQt6.QtCore import QTimer
        for it in self._body_items:
            it.setColor(color)
        QTimer.singleShot(ms, self._restore_color)

    def _restore_color(self) -> None:
        for it in self._body_items:
            it.setColor(self._body_color)
