"""
Convert a STEP (.stp/.step) CAD file to a light binary STL for the 3D viewport.

The app renders a triangle mesh, not native CAD, so the official VIVE Tracker
STEP file is tessellated once (offline) into `robotplay/assets/vive_tracker.stl`,
which is what the app loads at runtime. Re-run this only if you want to replace
the bundled model or change its mesh density.

Requires the `gmsh` wheel (bundles OpenCASCADE; not needed at runtime):
    pip install gmsh

Usage:
    python tools/convert_step_to_stl.py <input.stp> [output.stl]

The mesh is coarsened (MeshSizeMax ≈ 2.5 mm) so it stays light enough for smooth
60 Hz rendering; the STL loader recentres and scales it to fit, so absolute units
do not matter.
"""

from __future__ import annotations

import os
import sys


def convert(src: str, dst: str, size_max: float = 2.5, size_min: float = 0.6) -> None:
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.merge(src)                                   # import STEP via OCC
        gmsh.option.setNumber("Mesh.MeshSizeMin", size_min)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size_max)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.model.mesh.generate(2)                       # surface mesh
        gmsh.option.setNumber("Mesh.Binary", 1)
        gmsh.write(dst)
    finally:
        gmsh.finalize()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    if len(sys.argv) >= 3:
        dst = sys.argv[2]
    else:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dst = os.path.join(here, "robotplay", "assets", "vive_tracker.stl")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    print(f"Converting {src}\n        -> {dst}")
    convert(src, dst)
    print(f"Done. STL size: {os.path.getsize(dst) / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
