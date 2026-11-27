"""Primitives 2, 3 & 4: Bar distribution, mandrels/hooks, ACI 318M anchorage, BS 8666 cut lengths, BBS & takeoff."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


def _round_up_5mm(value_mm: float) -> float:
    return float(math.ceil(value_mm / 5.0) * 5.0)


def round_nearest_5mm(value_mm: float) -> int:
    return int(round(float(value_mm) / 5.0) * 5)


# ---------------------------------------------------------------------------
# Primitive 2: Bar Distribution & Spacing Engine (mm)
# ---------------------------------------------------------------------------


def distribute_bars(
    L_total_mm: float,
    c_edge_mm: float,
    d_b_mm: float,
    s_target_mm: float,
) -> dict[str, Any]:
    """Convert target spacing into symmetric, non-colliding bar centerlines across L_total_mm."""
    L_tot = float(L_total_mm)
    c_edge = float(c_edge_mm)
    db = float(d_b_mm)
    s_target = float(s_target_mm)

    if s_target <= 0.0:
        raise ValueError("E-DIST-01: s_target_mm must be positive")

    L_dist = L_tot - 2.0 * c_edge - db
    if L_dist <= 0.0:
        raise ValueError(f"E-DIST-01: L_dist={L_dist:.2f} mm <= 0")

    n_spaces = max(1, math.ceil(L_dist / s_target))
    n_bars = n_spaces + 1
    if n_bars < 2:
        raise ValueError("E-DIST-01: N_bars < 2")

    s_actual = L_dist / n_spaces
    x_0 = c_edge + db / 2.0
    positions = [round(x_0 + i * s_actual, 3) for i in range(n_bars)]

    return {
        "bar_count": n_bars,
        "n_spaces": n_spaces,
        "actual_spacing_mm": round(s_actual, 3),
        "first_bar_offset_mm": round(x_0, 3),
        "out_to_out_length_mm": round(L_tot - 2.0 * c_edge, 3),
        "positions_mm": positions,
    }


def compute_bar_distribution(
    span_mm: float,
    cover_mm: float,
    bar_dia_mm: float,
    spacing_mm: float,
) -> dict[str, Any]:
    """Alias for ``distribute_bars`` preserving Phase 2 Step 1 signature."""
    return distribute_bars(span_mm, cover_mm, bar_dia_mm, spacing_mm)


def distribute_discrete_bars(
    width_mm: float,
    c_nom_mm: float,
    d_b_link_mm: float,
    d_b_mm: float,
    n_bars: int,
) -> dict[str, Any]:
    """Distribute discrete longitudinal bars across a beam or column face inside links."""
    if n_bars < 2:
        raise ValueError("E-DIST-01: n_bars must be >= 2")
    b = float(width_mm)
    c_nom = float(c_nom_mm)
    d_link = float(d_b_link_mm)
    db = float(d_b_mm)

    inner = b - 2.0 * (c_nom + d_link) - db
    s_c2c = inner / (n_bars - 1)
    s_clear = s_c2c - db
    x_0 = c_nom + d_link + db / 2.0
    positions = [round(x_0 + i * s_c2c, 3) for i in range(n_bars)]

    return {
        "bar_count": n_bars,
        "s_c2c_mm": round(s_c2c, 3),
        "s_clear_mm": round(s_clear, 3),
        "positions_mm": positions,
    }


def distribute_multi_zone(
    L_span_mm: float,
    L_z1_mm: float,
    s_1_mm: float,
    s_2_mm: float,
    d_link_mm: float,
    c_end_mm: float = 50.0,
) -> dict[str, Any]:
    """Multi-zone stirrup/tie distribution with zero duplicate bars at zone boundaries."""
    L_span = float(L_span_mm)
    L_z1 = float(L_z1_mm)
    s_1 = float(s_1_mm)
    s_2 = float(s_2_mm)
    d_link = float(d_link_mm)
    c_end = float(c_end_mm)

    if L_z1 <= 0.0:
        # Uniform zone across entire span
        res = distribute_bars(L_span, c_end, d_link, s_1)
        return {
            "is_multi_zone": False,
            "n_end_total": res["bar_count"],
            "n_mid": 0,
            "s_1_act_mm": res["actual_spacing_mm"],
            "s_2_act_mm": res["actual_spacing_mm"],
            "end_positions_mm": res["positions_mm"],
            "mid_positions_mm": [],
        }

    x_0_end = c_end + d_link / 2.0
    L_dist_1 = L_z1 - x_0_end
    if L_dist_1 <= 0.0:
        raise ValueError("E-DIST-01: L_z1 too small for end offset")

    n_sp_1 = max(1, math.ceil(L_dist_1 / s_1))
    s_act_1 = L_dist_1 / n_sp_1
    left_end = [round(x_0_end + i * s_act_1, 3) for i in range(n_sp_1 + 1)]
    right_end = [round(L_span - x, 3) for x in reversed(left_end)]
    end_positions = left_end + right_end

    L_mid = L_span - 2.0 * L_z1
    if L_mid <= 0.0:
        return {
            "is_multi_zone": True,
            "n_end_total": len(end_positions),
            "n_mid": 0,
            "s_1_act_mm": round(s_act_1, 3),
            "s_2_act_mm": 0.0,
            "end_positions_mm": end_positions,
            "mid_positions_mm": [],
        }

    n_sp_2 = max(1, math.ceil(L_mid / s_2))
    s_act_2 = L_mid / n_sp_2
    mid_positions = [round(L_z1 + j * s_act_2, 3) for j in range(1, n_sp_2)]

    return {
        "is_multi_zone": True,
        "n_end_total": len(end_positions),
        "n_mid": len(mid_positions),
        "s_1_act_mm": round(s_act_1, 3),
        "s_2_act_mm": round(s_act_2, 3),
        "end_positions_mm": end_positions,
        "mid_positions_mm": mid_positions,
    }


# ---------------------------------------------------------------------------
# Primitive 3: Mandrels, Hooks, BS 8666 Cut Lengths & ACI 318M Anchorage
# ---------------------------------------------------------------------------


def min_bend_dia(bar_dia_mm: float, is_link: bool = False) -> float:
    """Standard inside bend diameter D_bend (mm) rounded up to nearest 5 mm."""
    db = float(bar_dia_mm)
    if is_link:
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


def standard_bend_diameter_mm(bar_dia_mm: float, is_tie_or_stirrup: bool = False) -> float:
    return min_bend_dia(bar_dia_mm, is_link=is_tie_or_stirrup)


def standard_hook_extension_mm(
    bar_dia_mm: float,
    angle_deg: int = 90,
    is_tie_or_stirrup: bool = False,
) -> float:
    """Standard hook straight tail extension (mm)."""
    db = float(bar_dia_mm)
    if angle_deg == 90:
        if is_tie_or_stirrup:
            return max(6.0 * db, 75.0)
        return 12.0 * db
    if angle_deg == 180:
        return max(4.0 * db, 65.0)
    if angle_deg == 135:
        return max(6.0 * db, 75.0)
    raise ValueError(f"Unsupported hook angle: {angle_deg}")


def standard_hook_leg_90_mm(bar_dia_mm: float, is_link: bool = False) -> float:
    """Out-to-out 90-deg hook leg H_90 (mm) rounded up to nearest 5 mm."""
    db = float(bar_dia_mm)
    d_bend = min_bend_dia(db, is_link=is_link)
    tail = standard_hook_extension_mm(db, angle_deg=90, is_tie_or_stirrup=is_link)
    return _round_up_5mm(db + d_bend / 2.0 + tail)


def bend_deduction_mm(
    d_b_mm: float,
    bend_angle_rad: float,
    is_link: bool = False,
    d_bend_mm: float | None = None,
) -> float:
    """Exact centerline bend deduction Delta(theta) = 2(R_bend + d_b)tan(theta/2) - theta(R_bend + d_b/2)."""
    db = float(d_b_mm)
    d_bend = float(d_bend_mm) if d_bend_mm is not None else min_bend_dia(db, is_link=is_link)
    r_bend = d_bend / 2.0
    return 2.0 * (r_bend + db) * math.tan(bend_angle_rad / 2.0) - bend_angle_rad * (r_bend + db / 2.0)


def cut_length_mm(
    shape_code: str,
    dims_mm: dict[str, float],
    d_b_mm: float,
    is_link: bool = False,
) -> int:
    """Exact centerline cutting length (mm) rounded to nearest 5 mm per BS 8666 / ACI 315."""
    sc = shape_code.upper()
    db = float(d_b_mm)
    d_bend = min_bend_dia(db, is_link=is_link)
    r_bend = d_bend / 2.0
    delta_90 = bend_deduction_mm(db, math.pi / 2.0, is_link=is_link, d_bend_mm=d_bend)

    A = float(dims_mm.get("A", 0.0))
    B = float(dims_mm.get("B", 0.0))
    C = float(dims_mm.get("C", 0.0))
    D = float(dims_mm.get("D", 0.0))

    if sc == "00":
        raw = A
    elif sc == "11":
        raw = A + B - delta_90
    elif sc == "12":
        raw = A - (r_bend + db) + math.pi * (r_bend + db / 2.0) + max(4.0 * db, 65.0)
    elif sc == "21":
        raw = A + B + C - 2.0 * delta_90
    elif sc == "23":
        if C <= 0.0:
            raise ValueError("Shape 23 requires C > 0")
        if B / C > 1.0 / 6.0 or B >= 75.0:
            raise ValueError(f"E-COL-OFFSET: Shape 23 slope B/C={B/C:.3f} or offset B={B} exceeds ACI 315 limits")
        theta = math.atan(B / C)
        delta_t = bend_deduction_mm(db, theta, is_link=is_link, d_bend_mm=d_bend)
        raw = A + D + math.hypot(B, C) - 2.0 * delta_t
    elif sc == "51":
        tail_135 = max(6.0 * db, 75.0)
        hook_term = tail_135 + (0.75 * math.pi) * (r_bend + db / 2.0) - (r_bend + db)
        raw = 2.0 * (A + B) - 3.0 * delta_90 + 2.0 * hook_term
    elif sc == "CT":
        tail_135 = max(6.0 * db, 75.0)
        hook_term = tail_135 + (0.75 * math.pi) * (r_bend + db / 2.0) - (r_bend + db)
        raw = A + 2.0 * hook_term
    else:
        raise ValueError(f"Unsupported shape_code: {shape_code}")

    return round_nearest_5mm(raw)


def calc_ld_tension(
    d_b_mm: float,
    fy_mpa: float,
    fc_mpa: float,
    c_b_mm: float,
    k_tr_mm: float = 0.0,
    psi_t: float = 1.0,
    lam: float = 1.0,
    psi_e: float = 1.0,
) -> float:
    """ACI 318M Eq. 25.4.2.3a tension development length (mm)."""
    db = float(d_b_mm)
    psi_s = 0.8 if db <= 19.0 else 1.0
    conf = min((float(c_b_mm) + float(k_tr_mm)) / db, 2.5)
    l_d = (float(fy_mpa) / (1.1 * lam * math.sqrt(float(fc_mpa)))) * ((psi_t * psi_e * psi_s) / conf) * db
    return round(max(l_d, 300.0), 1)


def calc_ldh_hook(
    d_b_mm: float,
    fy_mpa: float,
    fc_mpa: float,
    side_cover_mm: float = 75.0,
    tail_cover_mm: float = 75.0,
    confined: bool = False,
    lam: float = 1.0,
    psi_e: float = 1.0,
) -> float:
    """ACI 318M 25.4.3.1 standard hook tension development length (mm)."""
    db = float(d_b_mm)
    psi_c = 0.7 if (db <= 36.0 and side_cover_mm >= 65.0 and tail_cover_mm >= 50.0) else 1.0
    psi_r = 0.8 if confined else 1.0
    l_dh = (0.24 * float(fy_mpa) * psi_e * psi_c * psi_r / (lam * math.sqrt(float(fc_mpa)))) * db
    return round(max(l_dh, 8.0 * db, 150.0), 1)


def calc_ldc_compression(
    d_b_mm: float,
    fy_mpa: float,
    fc_mpa: float,
    lam: float = 1.0,
) -> float:
    """ACI 318M 25.4.9.2 compression development length (mm)."""
    db = float(d_b_mm)
    fy = float(fy_mpa)
    fc = float(fc_mpa)
    l_dc = max((0.24 * fy / (lam * math.sqrt(fc))) * db, 0.043 * fy * db, 200.0)
    return round(l_dc, 1)


def calc_lsc_compression_lap(
    d_b_mm: float,
    fy_mpa: float,
    fc_mpa: float,
) -> float:
    """ACI 318M 25.5.5.1 compression lap splice length (mm)."""
    db = float(d_b_mm)
    fy = float(fy_mpa)
    fc = float(fc_mpa)
    if db > 36.0:
        raise ValueError("Bars larger than 36 mm shall not be lap-spliced")
    base = max(0.071 * fy * db, 300.0) if fy <= 420.0 else max((0.13 * fy - 24.0) * db, 300.0)
    if fc < 21.0:
        base *= 4.0 / 3.0
    return round(base, 1)


# ---------------------------------------------------------------------------
# Primitive 4: Bar Bending Schedule (BBS) & Quantity Takeoff
# ---------------------------------------------------------------------------


def unit_mass_kg_per_m(bar_dia_mm: float) -> float:
    """Standard metric deformed bar linear mass: d_b^2 / 162.2 (kg/m)."""
    db = float(bar_dia_mm)
    return (db * db) / 162.2


def build_bbs_table(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build canonical Primitive 4 BBS rows and unrounded total steel mass (kg)."""
    rows: list[dict[str, Any]] = []
    total_unrounded = 0.0
    for item in items:
        dia = int(round(float(item["dia_mm"])))
        shape = str(item["shape_code"]).upper()
        is_link = bool(item.get("is_link", shape in {"51", "CT"}))
        dims = item.get("bend_dims_mm", {})
        cut_len = int(item["cut_length_mm"]) if "cut_length_mm" in item else cut_length_mm(shape, dims, dia, is_link=is_link)
        u_mass_raw = unit_mass_kg_per_m(dia)
        num_members = int(item.get("num_members", 1))
        bars_per_member = int(item["bars_per_member"])
        total_qty = num_members * bars_per_member
        row_mass_raw = total_qty * (cut_len / 1000.0) * u_mass_raw
        total_unrounded += row_mass_raw

        grade_prefix = str(item.get("grade_prefix", "R" if (is_link and dia <= 10 and item.get("mild_links", True)) else "T"))
        rows.append(
            {
                "bar_mark": str(item["bar_mark"]),
                "member_mark": str(item.get("member_mark", "")),
                "bar_type_grade": f"{grade_prefix}{dia}",
                "shape_code": shape,
                "dia_mm": dia,
                "spacing_mm": round(float(item["spacing_mm"]), 2) if item.get("spacing_mm") is not None else None,
                "num_members": num_members,
                "bars_per_member": bars_per_member,
                "total_qty": total_qty,
                "bend_dims_mm": {k: int(round(float(dims.get(k, 0)))) for k in ("A", "B", "C", "D", "E", "H")},
                "cut_length_mm": cut_len,
                "unit_mass_kg_m": round(u_mass_raw, 4),
                "total_mass_kg": round(row_mass_raw, 2),
                # Compatibility aliases for Drafting2D.add_bbs_table
                "mark": str(item["bar_mark"]),
                "type_size": f"{grade_prefix}{dia}",
                "no_off": total_qty,
            }
        )

    return {
        "rows": rows,
        "total_steel_kg": round(total_unrounded, 2),
    }


def compute_takeoff(
    structural_concrete_m3: float,
    blinding_concrete_m3: float,
    formwork_area_m2: float,
    total_steel_kg: float,
) -> dict[str, float]:
    """Compute canonical Primitive 4 member quantity takeoff summary."""
    sc = float(structural_concrete_m3)
    bc = float(blinding_concrete_m3)
    fa = float(formwork_area_m2)
    st = float(total_steel_kg)
    density = (st / sc) if sc > 0.0 else 0.0
    return {
        "structural_concrete_m3": round(sc, 4),
        "blinding_concrete_m3": round(bc, 4),
        "formwork_area_m2": round(fa, 3),
        "total_steel_kg": round(st, 2),
        "steel_density_kg_m3": round(density, 2),
    }


# ---------------------------------------------------------------------------
# Phase 2 Step 1 Compatibility Dataclass & Helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BarScheduleItem:
    """Single line item for legacy metric Bar Bending Schedule (BBS) callers."""

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
        dims = {}
        for key, val in zip(("A", "B", "C", "D"), self.legs_mm):
            dims[key] = float(val)
        return float(cut_length_mm(self.shape_code, dims, self.bar_dia_mm, is_link=self.is_tie_or_stirrup))


def build_bar_bending_schedule(items: list[BarScheduleItem]) -> list[dict[str, Any]]:
    raw_items = []
    for it in items:
        dims = {k: float(v) for k, v in zip(("A", "B", "C", "D"), it.legs_mm)}
        raw_items.append(
            {
                "bar_mark": it.mark,
                "grade_prefix": it.bar_type,
                "dia_mm": it.bar_dia_mm,
                "spacing_mm": it.spacing_mm,
                "num_members": 1,
                "bars_per_member": it.no_off,
                "shape_code": it.shape_code,
                "bend_dims_mm": dims,
                "is_link": it.is_tie_or_stirrup,
            }
        )
    return build_bbs_table(raw_items)["rows"]


def total_schedule_mass_kg(rows: list[dict[str, Any]]) -> float:
    return round(sum(float(r["total_mass_kg"]) for r in rows), 2)
