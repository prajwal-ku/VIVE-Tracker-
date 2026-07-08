"""
Mesh loading for the 3D scene — STL directly, STEP via gmsh.

`load_mesh(path)` returns `(vertices Nx3, faces Mx3)` for use with a
`pyqtgraph.opengl.MeshData`. STL (binary or ASCII) is parsed directly with no
dependencies. STEP (.stp/.step) is tessellated with gmsh (bundles OpenCASCADE)
into a temporary STL and loaded back — so any CAD the user drops in works, with
gmsh only required for STEP.
"""

from __future__ import annotations

import os
import struct
import tempfile

import numpy as np


def load_mesh(path: str) -> tuple[np.ndarray, np.ndarray]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".stl":
        return load_stl(path)
    if ext in (".stp", ".step"):
        return load_step(path)
    raise ValueError(f"Unsupported CAD format '{ext}'. Use .stl or .stp/.step.")


# ── STL ─────────────────────────────────────────────────────────
def load_stl(path: str) -> tuple[np.ndarray, np.ndarray]:
    with open(path, "rb") as f:
        data = f.read()
    if data[:5].lower() == b"solid" and b"facet" in data[:2000]:
        return _load_ascii_stl(data.decode("ascii", "ignore"))
    return _load_binary_stl(data)


def _load_binary_stl(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    n = struct.unpack("<I", data[80:84])[0]
    tri = np.dtype([("n", "<3f4"), ("v", "<3f4", (3,)), ("attr", "<u2")])
    tris = np.frombuffer(data, dtype=tri, count=n, offset=84)
    verts = tris["v"].reshape(-1, 3).astype(float)
    faces = np.arange(len(verts)).reshape(-1, 3)
    return verts, faces


def _load_ascii_stl(text: str) -> tuple[np.ndarray, np.ndarray]:
    verts = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("vertex"):
            _, x, y, z = line.split()[:4]
            verts.append((float(x), float(y), float(z)))
    verts = np.array(verts, dtype=float)
    faces = np.arange(len(verts)).reshape(-1, 3)
    return verts, faces


# ── STEP (via gmsh → temp STL) ──────────────────────────────────
def load_step(path: str) -> tuple[np.ndarray, np.ndarray]:
    try:
        import gmsh
    except Exception as e:  # pragma: no cover - depends on install
        raise ImportError(
            "Loading STEP (.stp/.step) needs the gmsh package: pip install gmsh"
        ) from e

    gmsh.initialize()
    tmp = None
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.merge(path)
        gmsh.option.setNumber("Mesh.MeshSizeMin", 0.6)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 3.0)
        gmsh.model.mesh.generate(2)
        fd, tmp = tempfile.mkstemp(suffix=".stl")
        os.close(fd)
        gmsh.option.setNumber("Mesh.Binary", 1)
        gmsh.write(tmp)
    finally:
        gmsh.finalize()

    try:
        return load_stl(tmp)
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
