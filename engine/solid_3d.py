"""3D NURBS / B-Rep solid modeling builder wrapping NVIDIA usd-brep."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import usd_brep  # noqa: F401 — must be imported before any pxr module


class Solid3DBuilder:
    """Safe wrapper around ``usd_brep`` primitives, booleans, fillets, and validation."""

    def create_box(
        self,
        origin: tuple[float, float, float],
        length: float,
        width: float,
        height: float,
    ) -> usd_brep.Brep:
        return usd_brep.create_box(origin, float(length), float(width), float(height))

    def create_cylinder(
        self,
        origin: tuple[float, float, float],
        radius: float,
        height: float,
    ) -> usd_brep.Brep:
        return usd_brep.create_cylinder(origin, float(radius), float(height))

    def boolean_difference(
        self,
        target: usd_brep.Brep,
        tool: usd_brep.Brep,
        keep_other_brep: bool = False,
    ) -> usd_brep.Brep:
        tool_arg = usd_brep.brep_copy(tool) if keep_other_brep else tool
        return usd_brep.boolean_difference(target, tool_arg)

    def boolean_union(
        self,
        brep1: usd_brep.Brep,
        brep2: usd_brep.Brep,
        keep_other_brep: bool = False,
    ) -> usd_brep.Brep:
        arg2 = usd_brep.brep_copy(brep2) if keep_other_brep else brep2
        return usd_brep.boolean_union(brep1, arg2)

    def circular_fillet(self, brep: usd_brep.Brep, radius: float) -> usd_brep.Brep:
        """Apply circular fillet in place, enforcing kernel radius bounds."""
        r = float(radius)
        if r < 8e-5:
            raise ValueError(f"Fillet radius {r} is below minimum kernel tolerance 8e-5")

        min_dim = float("inf")
        for edge in usd_brep.get_edges_via_api(brep):
            elen = float(usd_brep.edge_length(edge))
            if elen > 1e-6:
                min_dim = min(min_dim, elen)

        if min_dim < float("inf") and r > min_dim / 3.0:
            raise ValueError(
                f"Fillet radius {r} exceeds min_adjacent_face_dim / 3 ({min_dim / 3.0:.4f})"
            )

        return usd_brep.circular_fillet(brep, r)

    def assert_valid(self, brep: usd_brep.Brep) -> dict[str, Any]:
        """Validate that a Brep is a closed manifold solid with positive volume."""
        is_manifold = usd_brep.is_manifold_solid(brep)
        if not is_manifold:
            raise ValueError("Brep validation failed: geometry is not a closed manifold solid")

        volume = float(usd_brep.compute_volume(brep))
        if volume <= 0.0:
            raise ValueError(f"Brep validation failed: non-positive volume {volume}")

        bbox = usd_brep.brep_bounding_box(brep, tight=True)
        return {
            "is_manifold": is_manifold,
            "volume": volume,
            "bounding_box": bbox,
        }

    def tessellate(
        self,
        brep: usd_brep.Brep,
        chord_height_tolerance: float = 0.01,
    ) -> dict[str, Any]:
        poly = usd_brep.tessellate(brep, chord_height_tolerance=chord_height_tolerance)
        return poly.to_numpy_arrays()

    def export_usd(self, brep: usd_brep.Brep, path: str | Path) -> Path:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        usd_brep.usd.export_brep(brep, str(out_path))
        return out_path
