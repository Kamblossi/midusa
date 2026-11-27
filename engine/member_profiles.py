"""Primitive 1: PlaneGCS DOF == 0 concrete member profiles, net volumes (m^3), and formwork areas (m^2)."""

from __future__ import annotations

from typing import Any

from engine.sketch_bridge import SketchBridge


def solve_rect_profile(
    b_mm: float,
    h_mm: float,
    length_mm: float,
    clear_span_mm: float | None = None,
    is_column: bool = False,
    ends_exposed: bool = True,
) -> dict[str, Any]:
    """Solve a rectangular beam or column cross-section (DOF == 0) and compute V_c and A_f."""
    b = float(b_mm)
    h = float(h_mm)
    length = float(length_mm)
    if b <= 0.0 or h <= 0.0 or length <= 0.0:
        raise ValueError("b_mm, h_mm, and length_mm must be positive")

    sketch = SketchBridge()
    sketch.add_rectangle("rect", 0.0, 0.0, b, h, fix_origin=True)
    solved = sketch.solve(require_zero_dof=True)
    verts = [solved["points"][f"rect_p{i}"] for i in range(4)]

    vol_m3 = (b * h * length) / 1e9
    if is_column:
        h_clr = float(clear_span_mm) if clear_span_mm is not None else length
        form_m2 = 2.0 * (b + h) * h_clr / 1e6
    else:
        l_clr = float(clear_span_mm) if clear_span_mm is not None else length
        form_m2 = (b * l_clr + 2.0 * h * length) / 1e6
        if ends_exposed:
            form_m2 += (2.0 * b * h) / 1e6

    return {
        "profile_type": "RECT",
        "vertices": verts,
        "volume_m3": round(vol_m3, 6),
        "formwork_m2": round(form_m2, 6),
        "dof": solved["dof"],
        "status": solved["status"],
    }


def solve_flanged_profile(
    profile_type: str,
    b_w_mm: float,
    h_mm: float,
    b_f_mm: float,
    h_f_mm: float,
    length_mm: float,
    flange_side: str = "+Y",
) -> dict[str, Any]:
    """Solve a T_BEAM (8 vertices) or L_BEAM (6 vertices) cross-section (DOF == 0)."""
    ptype = profile_type.upper()
    bw = float(b_w_mm)
    h = float(h_mm)
    bf = float(b_f_mm)
    hf = float(h_f_mm)
    length = float(length_mm)

    if bf < bw or hf >= h or bw <= 0 or h <= 0 or length <= 0:
        raise ValueError("Invalid flanged beam dimensions")

    sketch = SketchBridge()
    if ptype == "T_BEAM":
        ov = (bf - bw) / 2.0
        coords = [
            (ov, 0.0),
            (ov + bw, 0.0),
            (ov + bw, h - hf),
            (bf, h - hf),
            (bf, h),
            (0.0, h),
            (0.0, h - hf),
            (ov, h - hf),
        ]
    elif ptype == "L_BEAM":
        if flange_side == "+Y":
            coords = [
                (0.0, 0.0),
                (bw, 0.0),
                (bw, h - hf),
                (bf, h - hf),
                (bf, h),
                (0.0, h),
            ]
        else:
            coords = [
                (bf - bw, 0.0),
                (bf, 0.0),
                (bf, h),
                (0.0, h),
                (0.0, h - hf),
                (bf - bw, h - hf),
            ]
    else:
        raise ValueError(f"Unsupported flanged profile_type: {profile_type}")

    pts = [sketch.add_point(f"p{i}", x, y, fixed=True) for i, (x, y) in enumerate(coords)]
    for i in range(len(pts)):
        p_a = pts[i]
        p_b = pts[(i + 1) % len(pts)]
        line = sketch.add_line(f"l{i}", p_a, p_b)
        if i % 2 == 0:
            sketch.constrain_horizontal(line)
        else:
            sketch.constrain_vertical(line)

    solved = sketch.solve(require_zero_dof=True)
    verts = [solved["points"][f"p{i}"] for i in range(len(coords))]
    area_mm2 = bw * (h - hf) + bf * hf
    vol_m3 = (area_mm2 * length) / 1e9
    form_m2 = ((bw + 2.0 * (h - hf) + (bf - bw) + 2.0 * hf) * length) / 1e6

    return {
        "profile_type": ptype,
        "vertices": verts,
        "volume_m3": round(vol_m3, 6),
        "formwork_m2": round(form_m2, 6),
        "dof": solved["dof"],
        "status": solved["status"],
    }


def solve_slab_profile(
    length_x_mm: float,
    length_y_mm: float,
    thickness_mm: float,
    opening_rects: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Solve a slab panel footprint (DOF == 0) with optional opening deductions."""
    lx = float(length_x_mm)
    ly = float(length_y_mm)
    h = float(thickness_mm)
    if lx <= 0 or ly <= 0 or h <= 0:
        raise ValueError("Slab dimensions must be positive")

    sketch = SketchBridge()
    sketch.add_rectangle("slab", 0.0, 0.0, lx, ly, fix_origin=True)
    solved = sketch.solve(require_zero_dof=True)
    verts = [solved["points"][f"slab_p{i}"] for i in range(4)]

    open_area = sum(float(ow) * float(ol) for ow, ol in (opening_rects or []))
    net_area = max(0.0, lx * ly - open_area)
    vol_m3 = (net_area * h) / 1e9
    form_m2 = (net_area + 2.0 * (lx + ly) * h) / 1e6

    return {
        "profile_type": "SLAB",
        "vertices": verts,
        "volume_m3": round(vol_m3, 6),
        "formwork_m2": round(form_m2, 6),
        "dof": solved["dof"],
        "status": solved["status"],
    }


def solve_pad_footing_profile(
    B_mm: float,
    L_mm: float,
    h_mm: float,
    t_b_mm: float = 50.0,
    p_b_mm: float = 50.0,
    step_w_mm: float = 0.0,
    step_l_mm: float = 0.0,
    step_h_mm: float = 0.0,
) -> dict[str, Any]:
    """Solve pad footing + blinding + optional pedestal/stub profile (DOF == 0)."""
    B, L, h = float(B_mm), float(L_mm), float(h_mm)
    t_b, p_b = float(t_b_mm), float(p_b_mm)
    sw, sl, sh = float(step_w_mm), float(step_l_mm), float(step_h_mm)

    sketch = SketchBridge()
    sketch.add_rectangle("pad", -B / 2.0, -L / 2.0, B, L, fix_origin=True)
    if sw > 0.0 and sl > 0.0:
        sketch.add_rectangle("step", -sw / 2.0, -sl / 2.0, sw, sl, fix_origin=True)
    solved = sketch.solve(require_zero_dof=True)

    vol_m3 = (B * L * h + sw * sl * sh) / 1e9
    blinding_m3 = ((B + 2.0 * p_b) * (L + 2.0 * p_b) * t_b) / 1e9
    form_m2 = (2.0 * (B + L) * h + 2.0 * (sw + sl) * sh) / 1e6

    return {
        "profile_type": "PAD_FOOTING",
        "vertices": [solved["points"][f"pad_p{i}"] for i in range(4)],
        "volume_m3": round(vol_m3, 6),
        "blinding_m3": round(blinding_m3, 6),
        "formwork_m2": round(form_m2, 6),
        "dof": solved["dof"],
        "status": solved["status"],
    }


def solve_retaining_wall_profile(
    H_s_mm: float,
    t_t_mm: float,
    t_b_mm: float,
    B_t_mm: float,
    B_h_mm: float,
    h_b_mm: float,
    w_k_mm: float = 0.0,
    d_k_mm: float = 0.0,
    L_w_mm: float = 5000.0,
    t_blind_mm: float = 50.0,
    p_blind_mm: float = 50.0,
) -> dict[str, Any]:
    """Solve cantilever retaining wall X-Z cross-section (DOF == 0) and compute V_c, V_blind, A_f."""
    H_s = float(H_s_mm)
    t_t = float(t_t_mm)
    t_b = float(t_b_mm)
    B_t = float(B_t_mm)
    B_h = float(B_h_mm)
    h_b = float(h_b_mm)
    w_k = float(w_k_mm)
    d_k = float(d_k_mm)
    L_w = float(L_w_mm)
    t_blind = float(t_blind_mm)
    p_blind = float(p_blind_mm)

    if t_b < t_t:
        raise ValueError(f"stem_base_thickness_mm ({t_b}) must be >= stem_top_thickness_mm ({t_t})")
    B_base = B_t + t_b + B_h
    if d_k > 0.0 and not (200.0 <= w_k <= B_base):
        raise ValueError(f"Shear key width ({w_k}) must satisfy 200 <= w_k <= B_base ({B_base})")

    # Closed X-Z polygon starting at toe front soffit (0, 0)
    coords: list[tuple[float, float]] = [
        (0.0, 0.0),
        (B_base, 0.0),
        (B_base, h_b),
        (B_t + t_b, h_b),
        (B_t + t_t, h_b + H_s),
        (B_t, h_b + H_s),
        (B_t, h_b),
        (0.0, h_b),
    ]
    if d_k > 0.0 and w_k > 0.0:
        kx0 = B_t + (t_b - w_k) / 2.0
        kx1 = kx0 + w_k
        coords = [
            (0.0, 0.0),
            (kx0, 0.0),
            (kx0, -d_k),
            (kx1, -d_k),
            (kx1, 0.0),
            (B_base, 0.0),
            (B_base, h_b),
            (B_t + t_b, h_b),
            (B_t + t_t, h_b + H_s),
            (B_t, h_b + H_s),
            (B_t, h_b),
            (0.0, h_b),
        ]

    sketch = SketchBridge()
    pts = [sketch.add_point(f"rw{i}", x, z, fixed=True) for i, (x, z) in enumerate(coords)]
    for i in range(len(pts)):
        sketch.add_line(f"l{i}", pts[i], pts[(i + 1) % len(pts)])
    solved = sketch.solve(require_zero_dof=True)
    verts = [solved["points"][f"rw{i}"] for i in range(len(coords))]

    area_xz = B_base * h_b + 0.5 * (t_t + t_b) * H_s + w_k * d_k
    vol_m3 = (area_xz * L_w) / 1e9
    blinding_m3 = ((B_base + 2.0 * p_blind) * t_blind * L_w) / 1e9
    form_m2 = ((2.0 * H_s + 2.0 * h_b + 2.0 * d_k) * L_w) / 1e6

    return {
        "profile_type": "RETAINING_WALL",
        "B_base_mm": B_base,
        "vertices": verts,
        "volume_m3": round(vol_m3, 6),
        "blinding_m3": round(blinding_m3, 6),
        "formwork_m2": round(form_m2, 6),
        "dof": solved["dof"],
        "status": solved["status"],
    }
