"""3D NURBS / B-Rep solid modeling builder wrapping NVIDIA usd-brep."""

from __future__ import annotations

import math
from pathlib import Path
import tempfile
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

    def create_bar_3d(
        self,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        radius: float,
    ) -> usd_brep.Brep:
        """Create a straight cylindrical rebar segment between two 3D points."""
        sx, sy, sz = (float(v) for v in start)
        ex, ey, ez = (float(v) for v in end)
        dx, dy, dz = ex - sx, ey - sy, ez - sz
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length <= 1e-6:
            raise ValueError("Bar start and end points must be distinct")

        cyl = usd_brep.create_cylinder((0.0, 0.0, 0.0), float(radius), length)
        ux, uy, uz = dx / length, dy / length, dz / length
        # Default cylinder is along +Z (0, 0, 1)
        dot = max(-1.0, min(1.0, uz))
        if abs(dot - 1.0) > 1e-7:
            if abs(dot + 1.0) <= 1e-7:
                cyl = usd_brep.rotate(cyl, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 180.0)
            else:
                ax_x = -uy
                ax_y = ux
                ax_z = 0.0
                angle_deg = math.degrees(math.acos(dot))
                cyl = usd_brep.rotate(cyl, (0.0, 0.0, 0.0), (ax_x, ax_y, ax_z), angle_deg)

        return usd_brep.translate(cyl, (sx, sy, sz))

    def create_l_bar_3d(
        self,
        p_start: tuple[float, float, float],
        p_corner: tuple[float, float, float],
        p_end: tuple[float, float, float],
        radius: float,
    ) -> usd_brep.Brep:
        """Create an L-shaped (90-deg hooked) rebar solid from two legs + corner sphere."""
        leg1 = self.create_bar_3d(p_start, p_corner, radius)
        leg2 = self.create_bar_3d(p_corner, p_end, radius)
        joint = usd_brep.create_sphere(p_corner, float(radius) * 1.001)
        combined = usd_brep.boolean_union(leg1, leg2)
        return usd_brep.boolean_union(combined, joint)

    def export_assembly_usd(
        self,
        prim_breps: dict[str, usd_brep.Brep],
        path: str | Path,
        default_prim: str = "World",
    ) -> Path:
        """Export named Breps into a hierarchical USD stage (e.g. /World/Footing/PadConcrete)."""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Build nested tree of Xforms -> leaf BrepArray blocks
        tree: dict[str, Any] = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            for idx, (prim_path, brep) in enumerate(prim_breps.items()):
                part_usda = tmp_root / f"part_{idx}.usda"
                usd_brep.usd.export_brep(brep, str(part_usda))
                raw = part_usda.read_text(encoding="utf-8")
                marker = 'def BrepArray "Brep0"'
                pos = raw.find(marker)
                if pos < 0:
                    raise RuntimeError(f"Failed to locate BrepArray block in {part_usda}")
                # Strip outer Xform "World" closing brace
                block = raw[pos:].rstrip()
                if block.endswith("}"):
                    block = block[:-1].rstrip()

                parts = [p for p in prim_path.strip("/").split("/") if p]
                leaf_name = parts[-1]
                block = block.replace(marker, f'def BrepArray "{leaf_name}"', 1)

                node = tree
                for p in parts[:-1]:
                    node = node.setdefault(p, {})
                node[leaf_name] = block

        def _render_tree(node: dict[str, Any], indent: int) -> list[str]:
            pad = "    " * indent
            lines: list[str] = []
            for key, val in node.items():
                if isinstance(val, str):
                    for line in val.splitlines():
                        lines.append(f"{pad}{line}" if line.strip() else "")
                else:
                    lines.append(f'{pad}def Xform "{key}"')
                    lines.append(f"{pad}{{")
                    lines.extend(_render_tree(val, indent + 1))
                    lines.append(f"{pad}}}")
            return lines

        header = [
            "#usda 1.0",
            "(",
            f'    defaultPrim = "{default_prim}"',
            "    metersPerUnit = 0.001",
            '    upAxis = "Z"',
            ")",
            "",
        ]
        body = _render_tree(tree, 0)
        out_path.write_text("\n".join(header + body) + "\n", encoding="utf-8")
        return out_path
