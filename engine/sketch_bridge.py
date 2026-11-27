"""2D parametric constraint solver bridge wrapping FreeCAD's PlaneGCS."""

from __future__ import annotations

from typing import Any

import planegcs


class SketchBridge:
    """High-level wrapper around ``planegcs.Sketch`` with named entities and DOF checks."""

    def __init__(self) -> None:
        self.sketch = planegcs.Sketch()
        self.points: dict[str, planegcs.PointId] = {}
        self.lines: dict[str, planegcs.LineId] = {}
        self.circles: dict[str, planegcs.CircleId] = {}
        self.params: dict[str, planegcs.ParamId] = {}

    def _resolve_point(self, ref: str | planegcs.PointId) -> planegcs.PointId:
        return self.points[ref] if isinstance(ref, str) else ref

    def _resolve_line(self, ref: str | planegcs.LineId) -> planegcs.LineId:
        return self.lines[ref] if isinstance(ref, str) else ref

    def _resolve_circle(self, ref: str | planegcs.CircleId) -> planegcs.CircleId:
        return self.circles[ref] if isinstance(ref, str) else ref

    def _resolve_param(self, value_or_name: float | str | planegcs.ParamId, fixed: bool = True) -> planegcs.ParamId:
        if isinstance(value_or_name, str):
            return self.params[value_or_name]
        if isinstance(value_or_name, (int, float)):
            return self.sketch.add_param(float(value_or_name), fixed=fixed)
        return value_or_name

    def add_param(self, name: str, value: float, fixed: bool = False) -> planegcs.ParamId:
        pid = self.sketch.add_param(float(value), fixed=fixed)
        self.params[name] = pid
        return pid

    def add_point(self, name: str, x: float, y: float, fixed: bool = False) -> planegcs.PointId:
        if fixed:
            pt_id = self.sketch.add_fixed_point(float(x), float(y))
        else:
            pt_id = self.sketch.add_point(float(x), float(y))
        self.points[name] = pt_id
        return pt_id

    def add_line(self, name: str, p1: str | planegcs.PointId, p2: str | planegcs.PointId) -> planegcs.LineId:
        line_id = self.sketch.add_line(self._resolve_point(p1), self._resolve_point(p2))
        self.lines[name] = line_id
        return line_id

    def add_circle(
        self,
        name: str,
        center: str | planegcs.PointId,
        radius: float | str | planegcs.ParamId,
        fixed_radius: bool = False,
    ) -> planegcs.CircleId:
        rad_param = self._resolve_param(radius, fixed=fixed_radius)
        cid = self.sketch.add_circle(self._resolve_point(center), rad_param)
        self.circles[name] = cid
        return cid

    def constrain_horizontal(self, line: str | planegcs.LineId) -> Any:
        return self.sketch.horizontal(self._resolve_line(line))

    def constrain_vertical(self, line: str | planegcs.LineId) -> Any:
        return self.sketch.vertical(self._resolve_line(line))

    def constrain_coincident(self, p1: str | planegcs.PointId, p2: str | planegcs.PointId) -> Any:
        return self.sketch.coincident(self._resolve_point(p1), self._resolve_point(p2))

    def constrain_p2p_distance(
        self,
        p1: str | planegcs.PointId,
        p2: str | planegcs.PointId,
        distance: float | str | planegcs.ParamId,
    ) -> Any:
        dist_param = self._resolve_param(distance, fixed=True)
        return self.sketch.p2p_distance(self._resolve_point(p1), self._resolve_point(p2), dist_param)

    def constrain_p2l_distance(
        self,
        pt: str | planegcs.PointId,
        line: str | planegcs.LineId,
        distance: float | str | planegcs.ParamId,
    ) -> Any:
        dist_param = self._resolve_param(distance, fixed=True)
        return self.sketch.p2l_distance(self._resolve_point(pt), self._resolve_line(line), dist_param)

    def constrain_circle_diameter(
        self,
        circle: str | planegcs.CircleId,
        diameter: float | str | planegcs.ParamId,
    ) -> Any:
        diam_param = self._resolve_param(diameter, fixed=True)
        return self.sketch.circle_diameter(self._resolve_circle(circle), diam_param)

    def constrain_circle_radius(
        self,
        circle: str | planegcs.CircleId,
        radius: float | str | planegcs.ParamId,
    ) -> Any:
        rad_param = self._resolve_param(radius, fixed=True)
        return self.sketch.circle_radius(self._resolve_circle(circle), rad_param)

    def add_rectangle(
        self,
        prefix: str,
        x0: float,
        y0: float,
        width: float,
        height: float,
        fix_origin: bool = True,
    ) -> dict[str, Any]:
        """Add a fully constrained axis-aligned rectangle from (x0, y0) with (width, height)."""
        p0 = self.add_point(f"{prefix}_p0", x0, y0, fixed=fix_origin)
        p1 = self.add_point(f"{prefix}_p1", x0 + width, y0)
        p2 = self.add_point(f"{prefix}_p2", x0 + width, y0 + height)
        p3 = self.add_point(f"{prefix}_p3", x0, y0 + height)

        l_bot = self.add_line(f"{prefix}_bottom", p0, p1)
        l_right = self.add_line(f"{prefix}_right", p1, p2)
        l_top = self.add_line(f"{prefix}_top", p2, p3)
        l_left = self.add_line(f"{prefix}_left", p3, p0)

        self.constrain_horizontal(l_bot)
        self.constrain_horizontal(l_top)
        self.constrain_vertical(l_right)
        self.constrain_vertical(l_left)

        self.constrain_p2p_distance(p0, p1, width)
        self.constrain_p2p_distance(p1, p2, height)

        return {
            "points": [f"{prefix}_p0", f"{prefix}_p1", f"{prefix}_p2", f"{prefix}_p3"],
            "lines": [f"{prefix}_bottom", f"{prefix}_right", f"{prefix}_top", f"{prefix}_left"],
        }

    def solve(self, require_zero_dof: bool = True) -> dict[str, Any]:
        """Solve the 2D constraint system and verify DOF == 0 when required."""
        status = self.sketch.solve()
        dof = self.sketch.dof()
        if status != planegcs.SolveStatus.Success:
            raise RuntimeError(f"PlaneGCS solve failed with status={status}, dof={dof}")
        if require_zero_dof and dof != 0:
            raise RuntimeError(f"Sketch is not fully constrained: DOF={dof} (expected 0)")

        return {
            "status": str(status),
            "dof": dof,
            "points": {name: self.get_point(name) for name in self.points},
            "circles": {name: self.get_circle(name) for name in self.circles},
        }

    def get_point(self, name: str | planegcs.PointId) -> tuple[float, float]:
        x, y = self.sketch.get_point(self._resolve_point(name))
        return (float(x), float(y))

    def get_circle(self, name: str | planegcs.CircleId) -> tuple[tuple[float, float], float]:
        info = self.sketch.get_circle(self._resolve_circle(name))
        cx, cy = info.center
        return ((float(cx), float(cy)), float(info.radius))

    def get_line(self, name: str | planegcs.LineId) -> tuple[tuple[float, float], tuple[float, float]]:
        info = self.sketch.get_line(self._resolve_line(name))
        return ((float(info.p1[0]), float(info.p1[1])), (float(info.p2[0]), float(info.p2[1])))
