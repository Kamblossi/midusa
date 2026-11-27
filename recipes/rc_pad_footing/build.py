"""Template 1: Parametric SI Metric RC Pad Footing (rc_pad_footing)."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import engine  # noqa: F401 — loads usd_brep before pxr
from engine.drafting_2d import Drafting2D
from engine.member_profiles import solve_pad_footing_profile
from engine.rebar_detailing import (
    build_bbs_table,
    calc_ld_tension,
    calc_ldc_compression,
    calc_ldh_hook,
    compute_takeoff,
    distribute_bars,
    standard_hook_leg_90_mm,
)
from engine.renderer import Renderer3D
from engine.solid_3d import Solid3DBuilder
from rules.validator import evaluate_rules


def _get(params: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in params:
            return params[k]
    return default


def _dowel_xy_positions(
    col_x0: float,
    col_y0: float,
    col_w: float,
    col_l: float,
    col_cover: float,
    dowel_count: int,
) -> list[tuple[float, float]]:
    x_min = col_x0 + col_cover
    x_max = col_x0 + col_w - col_cover
    y_min = col_y0 + col_cover
    y_max = col_y0 + col_l - col_cover
    x_mid = 0.5 * (x_min + x_max)
    y_mid = 0.5 * (y_min + y_max)

    corners = [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]
    if dowel_count == 4:
        return corners
    if dowel_count == 8:
        return corners + [(x_mid, y_min), (x_max, y_mid), (x_mid, y_max), (x_min, y_mid)]
    pts = list(corners)
    extra = max(0, dowel_count - 4)
    for i in range(extra):
        t = (i + 1) / (extra + 1)
        pts.append((x_min + t * (x_max - x_min), y_min if i % 2 == 0 else y_max))
    return pts[:dowel_count]


def build(params: dict[str, Any], out_dir: str | Path, render_3d: bool = True) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    mark = str(_get(params, "member_mark", default="PF-01"))
    B = float(_get(params, "pad_width_mm", "footing_width_mm", default=2400.0))
    L = float(_get(params, "pad_length_mm", "footing_length_mm", default=2400.0))
    h = float(_get(params, "pad_depth_mm", "footing_depth_mm", default=600.0))
    t_b = float(_get(params, "blinding_thickness_mm", default=50.0))
    p_b = float(_get(params, "blinding_projection_mm", default=50.0))
    c_w = float(_get(params, "col_width_mm", default=400.0))
    c_l = float(_get(params, "col_length_mm", "col_depth_mm", default=400.0))
    c_h = float(_get(params, "col_stub_height_mm", default=600.0))
    e_x = float(_get(params, "eccentricity_x_mm", default=0.0))
    e_y = float(_get(params, "eccentricity_y_mm", default=0.0))

    pad_cover = float(_get(params, "pad_cover_mm", "cover_mm", default=75.0))
    col_cover = float(_get(params, "col_cover_mm", default=40.0))
    d_mat = float(_get(params, "mat_bar_dia_mm", "bottom_bar_dia_mm", default=16.0))
    s_mat = float(_get(params, "mat_spacing_mm", "bottom_bar_spacing_mm", default=150.0))
    dowel_n = int(_get(params, "dowel_count", default=4))
    d_dowel = float(_get(params, "dowel_dia_mm", "dowel_bar_dia_mm", default=20.0))
    dowel_proj = float(_get(params, "dowel_top_proj_mm", "dowel_projection_mm", default=720.0))
    d_link = float(_get(params, "link_dia_mm", "link_bar_dia_mm", default=10.0))
    s_link = float(_get(params, "link_spacing_mm", default=150.0))

    fc_pad = float(_get(params, "fc_pad_mpa", "fc_footing_mpa", default=25.0))
    fc_col = float(_get(params, "fc_col_mpa", "fc_column_mpa", default=30.0))
    fy = float(_get(params, "fy_mpa", default=460.0))
    q_allow = float(_get(params, "q_allow_kpa", default=200.0))
    P_D = float(_get(params, "P_dead_kn", default=650.0))
    P_L = float(_get(params, "P_live_kn", default=350.0))

    # 1. Primitive 1: PlaneGCS DOF == 0 profile & exact volumes
    prof = solve_pad_footing_profile(B, L, h, t_b_mm=t_b, p_b_mm=p_b, step_w_mm=c_w, step_l_mm=c_l, step_h_mm=c_h)

    # 2. Primitive 2 & 3: Rebar distributions & BBS
    dist_b1 = distribute_bars(L, pad_cover, d_mat, s_mat)
    dist_b2 = distribute_bars(B, pad_cover, d_mat, s_mat)
    dist_l1 = distribute_bars(c_h, 50.0, d_link, s_link)

    h90_mat = standard_hook_leg_90_mm(d_mat, is_link=False)
    h90_dowel = standard_hook_leg_90_mm(d_dowel, is_link=False)
    a_b1 = B - 2.0 * pad_cover
    a_b2 = L - 2.0 * pad_cover
    dowel_pad_emb = h - pad_cover - 2.0 * d_mat
    a_dowel = dowel_pad_emb + c_h + dowel_proj
    a_link = c_w - 2.0 * col_cover
    b_link = c_l - 2.0 * col_cover

    bbs_res = build_bbs_table(
        [
            {
                "bar_mark": "B1",
                "member_mark": mark,
                "grade_prefix": "T",
                "dia_mm": d_mat,
                "spacing_mm": dist_b1["actual_spacing_mm"],
                "num_members": 1,
                "bars_per_member": dist_b1["bar_count"],
                "shape_code": "21",
                "bend_dims_mm": {"A": a_b1, "B": h90_mat, "C": h90_mat},
            },
            {
                "bar_mark": "B2",
                "member_mark": mark,
                "grade_prefix": "T",
                "dia_mm": d_mat,
                "spacing_mm": dist_b2["actual_spacing_mm"],
                "num_members": 1,
                "bars_per_member": dist_b2["bar_count"],
                "shape_code": "21",
                "bend_dims_mm": {"A": a_b2, "B": h90_mat, "C": h90_mat},
            },
            {
                "bar_mark": "D1",
                "member_mark": mark,
                "grade_prefix": "T",
                "dia_mm": d_dowel,
                "spacing_mm": None,
                "num_members": 1,
                "bars_per_member": dowel_n,
                "shape_code": "11",
                "bend_dims_mm": {"A": a_dowel, "B": h90_dowel},
            },
            {
                "bar_mark": "L1",
                "member_mark": mark,
                "grade_prefix": "R",
                "dia_mm": d_link,
                "spacing_mm": dist_l1["actual_spacing_mm"],
                "num_members": 1,
                "bars_per_member": dist_l1["bar_count"],
                "shape_code": "51",
                "bend_dims_mm": {"A": a_link, "B": b_link},
                "is_link": True,
            },
        ]
    )
    takeoff = compute_takeoff(
        structural_concrete_m3=prof["volume_m3"],
        blinding_concrete_m3=prof["blinding_m3"],
        formwork_area_m2=prof["formwork_m2"],
        total_steel_kg=bbs_res["total_steel_kg"],
    )

    # 3. Structural & Geotechnical Engineering Checks (ACI 318M)
    A_pad = (B * L) / 1e6
    q_net = (P_D + P_L) / A_pad
    q_gross = q_net + (prof["volume_m3"] * 24.0) / A_pad
    P_u = max(1.4 * P_D, 1.2 * P_D + 1.6 * P_L)
    q_nu = P_u / A_pad

    d_avg = h - pad_cover - d_mat
    b_0 = 2.0 * (c_w + d_avg) + 2.0 * (c_l + d_avg)
    A_punch_in = ((c_w + d_avg) * (c_l + d_avg)) / 1e6
    V_u_punch = q_nu * (A_pad - A_punch_in)
    v_u_punch = (1000.0 * V_u_punch) / (b_0 * d_avg)
    beta_c = max(c_w, c_l) / min(c_w, c_l)
    v_c_punch = min(0.33, 0.17 * (1.0 + 2.0 / beta_c), 0.083 * (40.0 * d_avg / b_0 + 2.0)) * math.sqrt(fc_pad)
    phi_v_c_punch = 0.75 * v_c_punch
    phi_V_c_punch = (phi_v_c_punch * b_0 * d_avg) / 1000.0

    x_crit = (B - c_w) / 2.0 - d_avg
    V_u_1w = q_nu * (L / 1000.0) * (max(0.0, x_crit) / 1000.0)
    phi_V_c_1w = 0.75 * (0.17 * math.sqrt(fc_pad) * L * d_avg) / 1000.0

    cant_x = (B - c_w) / 2.0 / 1000.0
    M_u = q_nu * (L / 1000.0) * (cant_x ** 2) / 2.0
    A_s_prov = dist_b1["bar_count"] * (math.pi * d_mat ** 2 / 4.0)
    A_s_min = 0.0018 * L * h
    a_block = (A_s_prov * fy) / (0.85 * fc_pad * L)
    phi_M_n = 0.90 * A_s_prov * fy * (d_avg - a_block / 2.0) / 1e6

    A_1 = (c_w * c_l)
    A_2_ratio = min(math.sqrt((B * L) / A_1), 2.0)
    phi_B_n_col = 0.65 * 0.85 * fc_col * A_1 / 1000.0
    phi_B_n_pad = 0.65 * 0.85 * fc_pad * A_1 * A_2_ratio / 1000.0

    l_d_avail = (B - c_w) / 2.0 - pad_cover
    l_d_req = calc_ld_tension(d_mat, fy, fc_pad, c_b_mm=min(pad_cover + d_mat / 2.0, dist_b1["actual_spacing_mm"] / 2.0))
    l_dh_req = calc_ldh_hook(d_mat, fy, fc_pad, side_cover_mm=pad_cover, tail_cover_mm=pad_cover)
    l_dc_pad = calc_ldc_compression(d_dowel, fy, fc_pad)

    # 4. 2D Drafting (DXF + PNG)
    draft = Drafting2D()
    # Plan view centered at (0, 0)
    draft.add_rectangle(-B / 2.0 - p_b, -L / 2.0 - p_b, B + 2.0 * p_b, L + 2.0 * p_b, layer="BLINDING")
    draft.add_rectangle(-B / 2.0, -L / 2.0, B, L, layer="CONCRETE_OUTLINE")
    col_x0 = e_x - c_w / 2.0
    col_y0 = e_y - c_l / 2.0
    draft.add_rectangle(col_x0, col_y0, c_w, c_l, layer="CONCRETE_OUTLINE")

    for py in dist_b1["positions_mm"]:
        y_pos = -L / 2.0 + py
        draft.add_line((-B / 2.0 + pad_cover, y_pos), (B / 2.0 - pad_cover, y_pos), layer="REBAR_MAIN")
    for px in dist_b2["positions_mm"]:
        x_pos = -B / 2.0 + px
        draft.add_line((x_pos, -L / 2.0 + pad_cover), (x_pos, L / 2.0 - pad_cover), layer="REBAR_MAIN")

    dowel_pts = _dowel_xy_positions(col_x0, col_y0, c_w, c_l, col_cover, dowel_n)
    for dx, dy in dowel_pts:
        draft.add_circle(dx, dy, d_dowel * 0.75, layer="REBAR_DOWELS", with_centerlines=False)

    draft.add_section_callout((-B / 2.0 - 200.0, 0.0), (B / 2.0 + 200.0, 0.0), label="A")
    draft.add_north_arrow((B / 2.0 + 350.0, L / 2.0 - 250.0), size=200.0)
    draft.add_linear_dim((0.0, -L / 2.0 - 260.0), (-B / 2.0, -L / 2.0), (B / 2.0, -L / 2.0), angle=0.0, text_height=50.0)
    draft.add_linear_dim((-B / 2.0 - 260.0, 0.0), (-B / 2.0, -L / 2.0), (-B / 2.0, L / 2.0), angle=90.0, text_height=50.0)
    draft.add_text_note(f"{mark} PLAN VIEW (METRIC - mm)", (-B / 2.0, L / 2.0 + 180.0), height=65.0)

    # Section A-A below Plan View
    sy0 = -L / 2.0 - h - c_h - 600.0
    draft.add_rectangle(-B / 2.0 - p_b, sy0 - t_b, B + 2.0 * p_b, t_b, layer="BLINDING")
    draft.add_rectangle(-B / 2.0, sy0, B, h, layer="CONCRETE_OUTLINE")
    draft.add_concrete_hatch([(-B / 2.0, sy0), (B / 2.0, sy0), (B / 2.0, sy0 + h), (-B / 2.0, sy0 + h)], scale=14.0, layer="CONCRETE_HATCH")
    draft.add_rectangle(col_x0, sy0 + h, c_w, c_h, layer="CONCRETE_OUTLINE")
    draft.add_concrete_hatch([(col_x0, sy0 + h), (col_x0 + c_w, sy0 + h), (col_x0 + c_w, sy0 + h + c_h), (col_x0, sy0 + h + c_h)], scale=12.0, layer="CONCRETE_HATCH")

    z_b1 = sy0 + pad_cover + d_mat / 2.0
    draft.add_hooked_rebar_polyline(
        [(-B / 2.0 + pad_cover, z_b1 + h90_mat), (-B / 2.0 + pad_cover, z_b1), (B / 2.0 - pad_cover, z_b1), (B / 2.0 - pad_cover, z_b1 + h90_mat)],
        width=d_mat,
        layer="REBAR_MAIN",
    )
    z_b2 = z_b1 + d_mat
    for px in dist_b2["positions_mm"]:
        draft.add_circle(-B / 2.0 + px, z_b2, d_mat / 2.0, layer="REBAR_MAIN", with_centerlines=False)

    z_dw_base = z_b2 + d_mat / 2.0 + d_dowel / 2.0
    z_dw_top = sy0 + h + c_h + dowel_proj
    for sign, x_edge in ((-1.0, col_x0 + col_cover), (1.0, col_x0 + c_w - col_cover)):
        draft.add_hooked_rebar_polyline(
            [(x_edge + sign * h90_dowel, z_dw_base), (x_edge, z_dw_base), (x_edge, z_dw_top)],
            width=d_dowel,
            layer="REBAR_DOWELS",
        )
    for lz in dist_l1["positions_mm"]:
        draft.add_line((col_x0 + col_cover - 10.0, sy0 + h + lz), (col_x0 + c_w - col_cover + 10.0, sy0 + h + lz), layer="REBAR_LINKS")

    draft.add_text_note("SECTION A-A (METRIC - mm)", (-B / 2.0, sy0 + h + c_h + 150.0), height=65.0)
    draft.draw_bbs_table((B / 2.0 + 700.0, L / 2.0), bbs_res["rows"])

    dxf_path, png2d_path = draft.export_dxf_and_png(out / "pad_footing.dxf", out / "pad_footing_2d.png")

    # 5. 3D B-Rep Assembly (Origin (0, 0, 0) at pad soffit centroid)
    builder = Solid3DBuilder()
    blinding_brep = builder.create_box((-B / 2.0 - p_b, -L / 2.0 - p_b, -t_b), B + 2.0 * p_b, L + 2.0 * p_b, t_b)
    pad_brep = builder.create_box((-B / 2.0, -L / 2.0, 0.0), B, L, h)
    col_brep = builder.create_box((col_x0, col_y0, h), c_w, c_l, c_h)

    builder.assert_valid(blinding_brep)
    builder.assert_valid(pad_brep)
    builder.assert_valid(col_brep)

    prim_breps: dict[str, Any] = {
        f"/World/{mark}/Blinding": blinding_brep,
        f"/World/{mark}/Concrete/Pad": pad_brep,
        f"/World/{mark}/Concrete/ColumnStub": col_brep,
    }
    render_parts: list[dict[str, Any]] = [
        {"brep": blinding_brep, "color": "#475569", "opacity": 0.45, "show_edges": True},
        {"brep": pad_brep, "color": "#94a3b8", "opacity": 0.25, "show_edges": True},
        {"brep": col_brep, "color": "#cbd5e1", "opacity": 0.25, "show_edges": True},
    ]
    rebar_breps: list[Any] = []

    z_3d_b1 = pad_cover + d_mat / 2.0
    for idx, py in enumerate(dist_b1["positions_mm"]):
        y_pos = -L / 2.0 + py
        bar = builder.create_bar_3d((-B / 2.0 + pad_cover, y_pos, z_3d_b1), (B / 2.0 - pad_cover, y_pos, z_3d_b1), d_mat / 2.0)
        rebar_breps.append(bar)
        prim_breps[f"/World/{mark}/RebarCage/B1_{idx:02d}"] = bar
        render_parts.append({"brep": bar, "color": "#ef4444", "opacity": 1.0, "metallic": 0.6})

    z_3d_b2 = pad_cover + 1.5 * d_mat + 0.5
    for idx, px in enumerate(dist_b2["positions_mm"]):
        x_pos = -B / 2.0 + px
        bar = builder.create_bar_3d((x_pos, -L / 2.0 + pad_cover, z_3d_b2), (x_pos, L / 2.0 - pad_cover, z_3d_b2), d_mat / 2.0)
        rebar_breps.append(bar)
        prim_breps[f"/World/{mark}/RebarCage/B2_{idx:02d}"] = bar
        render_parts.append({"brep": bar, "color": "#f59e0b", "opacity": 1.0, "metallic": 0.6})

    z_3d_dw_base = z_3d_b2 + d_mat / 2.0 + d_dowel / 2.0 + 0.5
    z_3d_dw_top = h + c_h + dowel_proj
    for idx, (dx, dy) in enumerate(dowel_pts):
        vx, vy = dx - e_x, dy - e_y
        if abs(vx) >= abs(vy):
            hx = dx + math.copysign(h90_dowel, vx if vx != 0 else 1.0)
            hy = dy
        else:
            hx = dx
            hy = dy + math.copysign(h90_dowel, vy if vy != 0 else 1.0)
        dowel = builder.create_l_bar_3d((hx, hy, z_3d_dw_base), (dx, dy, z_3d_dw_base), (dx, dy, z_3d_dw_top), d_dowel / 2.0)
        rebar_breps.append(dowel)
        prim_breps[f"/World/{mark}/RebarCage/D1_{idx:02d}"] = dowel
        render_parts.append({"brep": dowel, "color": "#38bdf8", "opacity": 1.0, "metallic": 0.65})

    clash_res = builder.check_clearance_and_clashes([pad_brep, col_brep], rebar_breps, cover_mm=col_cover)
    usd_path = builder.export_assembly_usd(prim_breps, out / "pad_footing.usd")

    render_paths: dict[str, Path] = {}
    if render_3d:
        render_paths = Renderer3D().render_assembly_views(render_parts, out / "renders", prefix="pad_footing", chord_height_tolerance=0.25)

    metrics = {
        "cover_earth_mm": pad_cover,
        "s_actual_mm": dist_b1["actual_spacing_mm"],
        "q_net_kpa": round(q_net, 2),
        "q_gross_kpa": round(q_gross, 2),
        "P_u_kn": round(P_u, 2),
        "q_nu_kpa": round(q_nu, 2),
        "d_avg_mm": round(d_avg, 1),
        "b_0_mm": round(b_0, 1),
        "V_u_punch_kn": round(V_u_punch, 2),
        "phi_V_c_punch_kn": round(phi_V_c_punch, 2),
        "v_u_punch_mpa": round(v_u_punch, 3),
        "phi_v_c_punch_mpa": round(phi_v_c_punch, 3),
        "x_crit_mm": round(x_crit, 1),
        "V_u_1w_kn": round(V_u_1w, 2),
        "phi_V_c_1w_kn": round(phi_V_c_1w, 2),
        "M_u_knm": round(M_u, 2),
        "phi_M_n_knm": round(phi_M_n, 2),
        "A_s_prov_mm2": round(A_s_prov, 1),
        "A_s_min_mm2": round(A_s_min, 1),
        "phi_B_n_pad_kn": round(phi_B_n_pad, 1),
        "phi_B_n_col_kn": round(phi_B_n_col, 1),
        "l_d_avail_mm": round(l_d_avail, 1),
        "l_d_req_mm": round(l_d_req, 1),
        "l_dh_req_mm": round(l_dh_req, 1),
        "dowel_pad_emb_mm": round(dowel_pad_emb, 1),
        "l_dc_pad_mm": round(l_dc_pad, 1),
        "rebar_to_rebar_overlap_vol": clash_res["rebar_to_rebar_overlap_vol"],
        "min_cover_brep": clash_res["min_cover_brep"],
        "cover_req_mm": col_cover,
    }
    compliance = evaluate_rules("rc_pad_footing", params, metrics)

    summary = {
        "member_mark": mark,
        "sketch_status": prof["status"],
        "sketch_dof": prof["dof"],
        "concrete_volumes_m3": {
            "blinding": takeoff["blinding_concrete_m3"],
            "pad_concrete": round(B * L * h / 1e9, 4),
            "column_stub": round(c_w * c_l * c_h / 1e9, 4),
            "total_structural": takeoff["structural_concrete_m3"],
        },
        "takeoff": takeoff,
        "bar_bending_schedule": bbs_res["rows"],
        "total_steel_mass_kg": takeoff["total_steel_kg"],
        "metrics": metrics,
        "compliance": compliance,
        "rebar_prim_count": len(rebar_breps),
        "outputs": {
            "dxf": str(dxf_path),
            "png_2d": str(png2d_path),
            "usd": str(usd_path),
            "renders": {k: str(v) for k, v in render_paths.items()},
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    ws = Path(__file__).resolve().parent
    params = json.loads((ws / "params.json").read_text(encoding="utf-8"))
    summary = build(params, ws)
    vols = summary["concrete_volumes_m3"]
    print(
        f"[RC Pad Footing] DOF={summary['sketch_dof']} | "
        f"Concrete={vols['total_structural']:.4f} m3 | "
        f"Total Steel={summary['total_steel_mass_kg']:.2f} kg | "
        f"Status={summary['compliance']['status']}"
    )


if __name__ == "__main__":
    main()
