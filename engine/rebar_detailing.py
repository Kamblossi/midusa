"""Shared ACI 315-99 / metric reinforced concrete detailing primitives (SI metric: mm, kg)."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


def _round_up_5mm(value_mm: float) -> float:
    return float(math.ceil(value_mm / 5.0) * 5.0)


def standard_bend_diameter_mm(bar_dia_mm: float, is_tie_or_stirrup: bool = False) -> float:
    """Return standard inside bend diameter (mm), rounded up to nearest 5 mm (ACI 315-99)."""
    db = float(bar_dia_mm)
    if is_tie_or_stirrup:
        if db <= 16.0:
            raw = 4.0 * db
        elif db <= 25.0:
            raw = 6.0 * db
        else:
            raw = 8.0 * db
    else:
        if db <= 25.0:
            raw = 6.0 * db
        elif db <= 36.0:
            raw = 8.0 * db
        else:
            raw = 10.0 * db
    return _round_up_5mm(raw)


def standard_hook_extension_mm(
    bar_dia_mm: float,
    angle_deg: int = 90,
    is_tie_or_stirrup: bool = False,
) -> float:
    """Return standard hook straight extension (mm) per ACI 315-99."""
    db = float(bar_dia_mm)
    if angle_deg == 90:
        if is_tie_or_stirrup and db <= 16.0:
            return max(6.0 * db, 75.0)
        return 12.0 * db
    if angle_deg == 180:
        return max(4.0 * db, 65.0)
    if angle_deg == 135:
        return max(6.0 * db, 75.0)
    raise ValueError(f"Unsupported standard hook angle: {angle_deg} deg (expected 90, 135, or 180)")


def compute_bar_distribution(
    span_mm: float,
    cover_mm: float,
    bar_dia_mm: float,
    spacing_mm: float,
) -> dict[str, Any]:
    """Compute uniform bar layout across a concrete span with symmetric end cover."""
    span = float(span_mm)
    cover = float(cover_mm)
    db = float(bar_dia_mm)
    target_spacing = float(spacing_mm)

    if target_spacing <= 0.0:
        raise ValueError("spacing_mm must be positive")
    out_to_out_length_mm = span - 2.0 * cover
    if out_to_out_length_mm <= db:
        raise ValueError(f"Net distribution length {out_to_out_length_mm} mm too small for bar {db} mm")

    # Center-to-center travel between first and last bar
    c2c_span = out_to_out_length_mm - db
    spaces = max(1, math.ceil(c2c_span / target_spacing))
    bar_count = spaces + 1
    actual_spacing = c2c_span / spaces
    first_bar_offset = cover + db / 2.0
    positions_mm = [round(first_bar_offset + i * actual_spacing, 3) for i in range(bar_count)]

    return {
        "bar_count": bar_count,
        "actual_spacing_mm": round(actual_spacing, 3),
        "first_bar_offset_mm": round(first_bar_offset, 3),
        "out_to_out_length_mm": round(out_to_out_length_mm, 3),
        "positions_mm": positions_mm,
    }


@dataclass(frozen=True)
class BarScheduleItem:
    """Single line item for a metric Bar Bending Schedule (BBS)."""

    mark: str
    bar_type: str
    bar_dia_mm: float
    no_off: int
    spacing_mm: float | None
    shape_code: str
    legs_mm: tuple[float, ...]
    is_tie_or_stirrup: bool = False
    bend_count: int = 0

    def cut_length_mm(self) -> float:
        """Compute cut length (mm) from leg dimensions minus standard bend deductions."""
        total_legs = sum(float(x) for x in self.legs_mm)
        if self.bend_count <= 0:
            return round(total_legs, 0)
        # Approximate 90-deg bend allowance deduction (~ 1.0 * db per 90-deg bend)
        deduction = self.bend_count * 1.0 * float(self.bar_dia_mm)
        return round(max(total_legs - deduction, 0.0), 0)


def unit_mass_kg_per_m(bar_dia_mm: float) -> float:
    """Standard metric deformed bar linear mass: d_b^2 / 162.2 (kg/m)."""
    db = float(bar_dia_mm)
    return (db * db) / 162.2


def build_bar_bending_schedule(items: list[BarScheduleItem]) -> list[dict[str, Any]]:
    """Compute metric Bar Bending Schedule rows with cut length, unit mass, item mass, and total mass."""
    rows: list[dict[str, Any]] = []
    for item in items:
        cut_len_mm = item.cut_length_mm()
        unit_mass = unit_mass_kg_per_m(item.bar_dia_mm)
        item_mass = (cut_len_mm / 1000.0) * unit_mass
        total_mass = item_mass * item.no_off
        rows.append(
            {
                "mark": item.mark,
                "type_size": f"{item.bar_type}{int(round(item.bar_dia_mm))}",
                "bar_dia_mm": float(item.bar_dia_mm),
                "no_off": int(item.no_off),
                "spacing_mm": item.spacing_mm,
                "shape_code": item.shape_code,
                "cut_length_mm": round(cut_len_mm, 1),
                "unit_mass_kg_per_m": round(unit_mass, 4),
                "item_mass_kg": round(item_mass, 3),
                "total_mass_kg": round(total_mass, 2),
            }
        )
    return rows


def total_schedule_mass_kg(rows: list[dict[str, Any]]) -> float:
    """Return total steel mass (kg) summed across all BBS rows."""
    return round(sum(float(r["total_mass_kg"]) for r in rows), 2)
