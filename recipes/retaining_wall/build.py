"""Template 5A: Parametric SI Metric Cantilever Retaining Wall (retaining_wall)."""

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
from engine.member_profiles import solve_retaining_wall_profile
from engine.rebar_detailing import build_bbs_table, compute_takeoff, distribute_bars
from engine.renderer import Renderer3D
from engine.solid_3d import Solid3DBuilder
from rules.validator import evaluate_rules


def build(params: dict[str, Any], out_dir: str | Path, render_3d: bool = True) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    mark = str(params.get("member_mark", "RW-01"))
    L_w = float(params["wall_length_mm"])
    H_s = float(params["stem_height_mm"])
    t_t = float(params["stem_top_thick_mm"])
    t_b = float(params["stem_base_thick_mm"])
    B_t = float(params["toe_width_mm"])
    B_h = float(params["heel_width_mm"])
    h_b = float(params["base_thick_mm"])
    w_k = float(params.get("shear_key_width_mm", 0.0))
    d_k = float(params.get("shear_key_depth_mm", 0.0))
    t_blind = float(params.get("blinding_thick_mm", 50.0))
    p_blind = float(params.get("blinding_proj_mm", 50.0))

    cov_earth = float(params["cover_earth_mm"])
    cov_exp = float(params["cover_exposed_mm"])
    d_s1 = float(params["s1_dia_mm"])
    s_s1 = float(params["s1_spacing_mm"])
    d_dist = float(params["dist_dia_mm"])
    s_dist = float(params["dist_spacing_mm"])

    gamma_soil = float(params["gamma_soil_kn_m3"])
    phi_deg = float(params["phi_deg"])
    q_sur = float(params["q_surcharge_kpa"])
    mu = float(params["mu_base_friction"])
    q_allow = float(params["q_allow_kpa"])
    fc = float(params["fc_mpa"])
    fy = float(params["fy_mpa"])

    # 1. Primitive 1: PlaneGCS DOF == 0 profile
    prof = solve_retaining_wall_profile(H_s, t_t, t_b, B_t, B_h, h_b, w_k, d_k, L_w, t_blind, p_blind)
    B_base = prof["B_base_mm"]

    # 2. Rankine Geotechnical & Stem ULS Checks
    H_m = (H_s + h_b) / 1000.0
    phi_rad = math.radians(phi_deg)
    K_a = math.tan(math.pi / 4.0 - phi_rad / 2.0) ** 2
    K_p = math.tan(math.pi / 4.0 + phi_rad / 2.0) ** 2

    P_a_soil = 0.5 * K_a * gamma_soil * (H_m ** 2)
    P_a_q = K_a * q_sur * H_m
    P_a = P_a_soil + P_a_q
    M_ot = P_a_soil * (H_m / 3.0) + P_a_q * (H_m / 2.0)

    # Stabilizing weights (kN/m) excluding heel surcharge
    gamma_c = 24.0
    W_base = (B_base / 1000.0) * (h_b / 1000.0) * gamma_c
    W_stem = (0.5 * (t_t + t_b) / 1000.0) * (H_s / 1000.0) * gamma_c
    W_key = (w_k / 1000.0) * (d_k / 1000.0) * gamma_c
    W_soil = (B_h / 1000.0) * (H_s / 1000.0) * gamma_soil

    x_base = B_base / 2000.0
    x_stem = (B_t + 0.5 * t_b) / 1000.0
    x_key = (B_t + 0.5 * t_b) / 1000.0
    x_soil = (B_t + t_b + 0.5 * B_h) / 1000.0

    W_tot = W_base + W_stem + W_key + W_soil
    M_stab = W_base * x_base + W_stem * x_stem + W_key * x_key + W_soil * x_soil
    FoS_OT = M_stab / M_ot

    x_res = (M_stab - M_ot) / W_tot
    B_m = B_base / 1000.0
    e_m = B_m / 2.0 - x_res
    e_mm = e_m * 1000.0
    q_max = (W_tot / B_m) * (1.0 + 6.0 * e_m / B_m)
    q_min = (W_tot / B_m) * (1.0 - 6.0 * e_m / B_m)

    P_p_key = (
        0.5 * K_p * gamma_soil * (((h_b + d_k) / 1000.0) ** 2 - (h_b / 1000.0) ** 2)
        if d_k > 0.0
        else 0.0
    )
    FoS_SL = (mu * W_tot + P_p_key) / P_a

    # Stem base ULS shear & bending (factored 1.6 * lateral)
    Hs_m = H_s / 1000.0
    V_u_stem = 1.6 * (0.5 * K_a * gamma_soil * Hs_m ** 2 + K_a * q_sur * Hs_m)
    M_u_stem = 1.6 * (0.5 * K_a * gamma_soil * Hs_m ** 3 / 3.0 + K_a * q_sur * Hs_m ** 2 / 2.0)
    d_stem = t_b - cov_earth - d_s1 / 2.0
    phi_V_c_stem = 0.75 * (0.17 * math.sqrt(fc) * 1000.0 * d_stem) / 1000.0
    A_s_stem = (math.pi * d_s1 ** 2 / 4.0) * (1000.0 / s_s1)
    a_stem = (A_s_stem * fy) / (0.85 * fc * 1000.0)
    phi_M_n_stem = 0.90 * A_s_stem * fy * (d_stem - a_stem / 2.0) / 1e6

    # 3. Primitive 2 & 3: Rebar distribution & BBS over wall_length_mm (5 m)
    dist_s1 = distribute_bars(L_w, 50.0, d_s1, s_s1)
    dist_s2 = distribute_bars(L_w, 50.0, d_dist, s_dist)
    dist_s3 = distribute_bars(H_s, 50.0, d_dist, s_dist)
    dist_d1_bot = distribute_bars(B_base, 75.0, d_dist, s_dist)
    dist_d1_top = distribute_bars(B_h, 50.0, d_dist, s_dist)

    s1_a = H_s + h_b - cov_exp - cov_earth - d_dist
    s1_b = B_t + t_b - cov_exp - cov_earth
    s2_b = 195.0  # T12 90-deg standard leg
    h1_a = B_h + t_b - cov_earth - cov_exp
    h1_b = h_b - cov_earth - cov_exp
    t1_a = B_base - 2.0 * cov_exp
    t1_b = h_b - cov_earth - cov_exp
    long_run = L_w - 2.0 * cov_exp

    bbs_res = build_bbs_table(
        [
            {"bar_mark": "S1", "member_mark": mark, "grade_prefix": "T", "dia_mm": d_s1, "spacing_mm": dist_s1["actual_spacing_mm"], "num_members": 1, "bars_per_member": dist_s1["bar_count"], "shape_code": "11", "bend_dims_mm": {"A": s1_a, "B": s1_b}},
            {"bar_mark": "S2", "member_mark": mark, "grade_prefix": "T", "dia_mm": d_dist, "spacing_mm": dist_s2["actual_spacing_mm"], "num_members": 1, "bars_per_member": dist_s2["bar_count"], "shape_code": "11", "bend_dims_mm": {"A": s1_a, "B": s2_b}},
            {"bar_mark": "S3", "member_mark": mark, "grade_prefix": "T", "dia_mm": d_dist, "spacing_mm": dist_s3["actual_spacing_mm"], "num_members": 1, "bars_per_member": 2 * dist_s3["bar_count"], "shape_code": "00", "bend_dims_mm": {"A": long_run}},
            {"bar_mark": "H1", "member_mark": mark, "grade_prefix": "T", "dia_mm": d_s1, "spacing_mm": dist_s1["actual_spacing_mm"], "num_members": 1, "bars_per_member": dist_s1["bar_count"], "shape_code": "11", "bend_dims_mm": {"A": h1_a, "B": h1_b}},
            {"bar_mark": "T1", "member_mark": mark, "grade_prefix": "T", "dia_mm": d_s1, "spacing_mm": dist_s1["actual_spacing_mm"], "num_members": 1, "bars_per_member": dist_s1["bar_count"], "shape_code": "11", "bend_dims_mm": {"A": t1_a, "B": t1_b}},
            {"bar_mark": "D1", "member_mark": mark, "grade_prefix": "T", "dia_mm": d_dist, "spacing_mm": s_dist, "num_members": 1, "bars_per_member": dist_d1_bot["bar_count"] + dist_d1_top["bar_count"], "shape_code": "00", "bend_dims_mm": {"A": long_run}},
        ]
    )
    takeoff = compute_takeoff(prof["volume_m3"], prof["blinding_m3"], prof["formwork_m2"], bbs_res["total_steel_kg"])

    # 4. 2D Drafting (X-Z Cross-Section)
    draft = Drafting2D()
    draft.add_rectangle(-p_blind, -t_blind, B_base + 2.0 * p_blind, t_blind, layer="BLINDING")
    draft.add_concrete_hatch(prof["vertices"], scale=15.0, layer="CONCRETE_HATCH")
    for i in range(len(prof["vertices"])):
        draft.add_line(prof["vertices"][i], prof["vertices"][(i + 1) % len(prof["vertices"])], layer="CONCRETE_OUTLINE")

    x_s1 = B_t + t_b - cov_earth - d_s1 / 2.0
    draft.add_hooked_rebar_polyline([(x_s1 - s1_b, cov_earth), (x_s1, cov_earth), (x_s1, h_b + H_s - cov_exp)], width=d_s1, layer="REBAR_MAIN")
    draft.add_text_note(f"{mark} CROSS-SECTION (METRIC - mm)", (0.0, h_b + H_s + 200.0), height=65.0)
    draft.draw_bbs_table((B_base + 500.0, h_b + H_s), bbs_res["rows"])
    dxf_path, png2d_path = draft.export_dxf_and_png(out / "retaining_wall.dxf", out / "retaining_wall_2d.png")

    # 5. 3D B-Rep Assembly
    builder = Solid3DBuilder()
    blind_brep = builder.create_box((-p_blind, 0.0, -t_blind), B_base + 2.0 * p_blind, L_w, t_blind)
    base_brep = builder.create_box((0.0, 0.0, 0.0), B_base, L_w, h_b)
    stem_brep = builder.create_box((B_t, 0.0, h_b), t_b, L_w, H_s)
    builder.assert_valid(blind_brep)
    builder.assert_valid(base_brep)
    builder.assert_valid(stem_brep)

    prim_breps: dict[str, Any] = {
        f"/World/{mark}/Blinding": blind_brep,
        f"/World/{mark}/Concrete/Base": base_brep,
        f"/World/{mark}/Concrete/Stem": stem_brep,
    }
    render_parts: list[dict[str, Any]] = [
        {"brep": blind_brep, "color": "#475569", "opacity": 0.45, "show_edges": True},
        {"brep": base_brep, "color": "#94a3b8", "opacity": 0.25, "show_edges": True},
        {"brep": stem_brep, "color": "#cbd5e1", "opacity": 0.25, "show_edges": True},
    ]
    rebar_breps: list[Any] = []
    for idx, yp in enumerate(dist_s1["positions_mm"]):
        z_bot = cov_earth + d_s1 / 2.0
        z_top = h_b + H_s - cov_exp - d_s1 / 2.0
        x_toe_end = max(cov_exp + d_s1 / 2.0, x_s1 - s1_b)
        bar = builder.create_l_bar_3d((x_toe_end, yp, z_bot), (x_s1, yp, z_bot), (x_s1, yp, z_top), d_s1 / 2.0)
        rebar_breps.append(bar)
        prim_breps[f"/World/{mark}/RebarCage/S1_{idx:02d}"] = bar
        render_parts.append({"brep": bar, "color": "#ef4444", "opacity": 1.0, "metallic": 0.6})

    clash_res = builder.check_clearance_and_clashes([base_brep, stem_brep], rebar_breps, cover_mm=cov_exp)
    usd_path = builder.export_assembly_usd(prim_breps, out / "retaining_wall.usd")

    render_paths: dict[str, Path] = {}
    if render_3d:
        render_paths = Renderer3D().render_assembly_views(render_parts, out / "renders", prefix="retaining_wall", chord_height_tolerance=0.4)

    metrics = {
        "B_base_mm": B_base,
        "P_a_kn_m": round(P_a, 2),
        "M_ot_knm_m": round(M_ot, 2),
        "W_tot_kn_m": round(W_tot, 2),
        "M_stab_knm_m": round(M_stab, 2),
        "FoS_OT": round(FoS_OT, 2),
        "FoS_SL": round(FoS_SL, 2),
        "eccentricity_mm": round(e_mm, 1),
        "q_max_kpa": round(q_max, 2),
        "q_min_kpa": round(q_min, 2),
        "V_u_stem_kn_m": round(V_u_stem, 2),
        "phi_V_c_stem_kn_m": round(phi_V_c_stem, 2),
        "M_u_knm": round(M_u_stem, 2),
        "phi_M_n_knm": round(phi_M_n_stem, 2),
        "A_s_prov_mm2": round(A_s_stem, 1),
        "A_s_min_mm2": round(0.0018 * 1000.0 * t_b, 1),
        "rebar_to_rebar_overlap_vol": clash_res["rebar_to_rebar_overlap_vol"],
        "min_cover_brep": clash_res["min_cover_brep"],
        "cover_req_mm": cov_exp,
    }
    compliance = evaluate_rules("retaining_wall", params, metrics)

    summary = {
        "member_mark": mark,
        "sketch_status": prof["status"],
        "sketch_dof": prof["dof"],
        "takeoff": takeoff,
        "bar_bending_schedule": bbs_res["rows"],
        "total_steel_mass_kg": takeoff["total_steel_kg"],
        "metrics": metrics,
        "compliance": compliance,
        "outputs": {"dxf": str(dxf_path), "png_2d": str(png2d_path), "usd": str(usd_path), "renders": {k: str(v) for k, v in render_paths.items()}},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    ws = Path(__file__).resolve().parent
    params = json.loads((ws / "params.json").read_text(encoding="utf-8"))
    summary = build(params, ws)
    print(
        f"[Retaining Wall] DOF={summary['sketch_dof']} | Conc={summary['takeoff']['structural_concrete_m3']:.3f} m3 | "
        f"Steel={summary['total_steel_mass_kg']:.2f} kg | FoS_OT={summary['metrics']['FoS_OT']} | "
        f"FoS_SL={summary['metrics']['FoS_SL']} | Status={summary['compliance']['status']}"
    )


if __name__ == "__main__":
    main()
