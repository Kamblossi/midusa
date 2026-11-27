"""Template 2: Parametric SI Metric RC Beam (rc_beam)."""

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
from engine.member_profiles import solve_flanged_profile, solve_rect_profile
from engine.rebar_detailing import (
    build_bbs_table,
    calc_ldh_hook,
    compute_takeoff,
    distribute_discrete_bars,
    distribute_multi_zone,
    standard_hook_leg_90_mm,
)
from engine.renderer import Renderer3D
from engine.solid_3d import Solid3DBuilder
from rules.validator import evaluate_rules


def build(params: dict[str, Any], out_dir: str | Path, render_3d: bool = True) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    mark = str(params.get("member_mark", "B-01"))
    L_clr = float(params["clear_span_mm"])
    w_sup_L = float(params["support_width_left_mm"])
    w_sup_R = float(params["support_width_right_mm"])
    L_tot = w_sup_L + L_clr + w_sup_R

    b = float(params["width_mm"])
    h = float(params["depth_mm"])
    flange_type = str(params.get("flange_type", "RECT")).upper()
    cover = float(params["cover_mm"])

    n_bot = int(params["bot_bar_count"])
    d_bot = float(params["bot_bar_dia_mm"])
    n_top = int(params["top_bar_count"])
    d_top = float(params["top_bar_dia_mm"])
    d_link = float(params["link_dia_mm"])
    L_z1 = float(params.get("link_end_zone_mm", 0.0))
    s_1 = float(params["link_end_spacing_mm"])
    s_2 = float(params["link_mid_spacing_mm"])
    fc = float(params["fc_mpa"])
    fy = float(params["fy_mpa"])

    # 1. Primitive 1: PlaneGCS DOF == 0 profile
    if flange_type in {"T_BEAM", "L_BEAM"}:
        prof = solve_flanged_profile(
            flange_type, b, h, float(params["flange_width_mm"]), float(params["flange_thick_mm"]), L_tot
        )
    else:
        prof = solve_rect_profile(b, h, L_tot, clear_span_mm=L_clr, is_column=False, ends_exposed=True)

    # 2. Primitive 2 & 3: Bar distribution & BBS
    bot_dist = distribute_discrete_bars(b, cover, d_link, d_bot, n_bot)
    top_dist = distribute_discrete_bars(b, cover, d_link, d_top, n_top)
    stirrups = distribute_multi_zone(L_clr, L_z1, s_1, s_2, d_link, c_end_mm=50.0)

    a_long = L_tot - 2.0 * cover
    h90_bot = standard_hook_leg_90_mm(d_bot, is_link=False)
    h90_top = standard_hook_leg_90_mm(d_top, is_link=False)
    a_link = b - 2.0 * cover
    b_link = h - 2.0 * cover

    bbs_items: list[dict[str, Any]] = [
        {
            "bar_mark": "B1",
            "member_mark": mark,
            "grade_prefix": "T",
            "dia_mm": d_bot,
            "spacing_mm": None,
            "num_members": 1,
            "bars_per_member": n_bot,
            "shape_code": "21",
            "bend_dims_mm": {"A": a_long, "B": h90_bot, "C": h90_bot},
        },
        {
            "bar_mark": "T1",
            "member_mark": mark,
            "grade_prefix": "T",
            "dia_mm": d_top,
            "spacing_mm": None,
            "num_members": 1,
            "bars_per_member": n_top,
            "shape_code": "21",
            "bend_dims_mm": {"A": a_long, "B": h90_top, "C": h90_top},
        },
        {
            "bar_mark": "L1",
            "member_mark": mark,
            "grade_prefix": "R",
            "dia_mm": d_link,
            "spacing_mm": stirrups["s_1_act_mm"],
            "num_members": 1,
            "bars_per_member": stirrups["n_end_total"],
            "shape_code": "51",
            "bend_dims_mm": {"A": a_link, "B": b_link},
            "is_link": True,
        },
    ]
    if stirrups["n_mid"] > 0:
        bbs_items.append(
            {
                "bar_mark": "L2",
                "member_mark": mark,
                "grade_prefix": "R",
                "dia_mm": d_link,
                "spacing_mm": stirrups["s_2_act_mm"],
                "num_members": 1,
                "bars_per_member": stirrups["n_mid"],
                "shape_code": "51",
                "bend_dims_mm": {"A": a_link, "B": b_link},
                "is_link": True,
            }
        )

    bbs_res = build_bbs_table(bbs_items)
    takeoff = compute_takeoff(prof["volume_m3"], 0.0, prof["formwork_m2"], bbs_res["total_steel_kg"])

    # 3. Structural checks
    d_eff = h - cover - d_link - d_bot / 2.0
    A_s_bot = n_bot * (math.pi * d_bot ** 2 / 4.0)
    rho = A_s_bot / (b * d_eff)
    rho_min = max(0.25 * math.sqrt(fc) / fy, 1.4 / fy)
    s_1_max_seis = min(d_eff / 4.0, 8.0 * d_bot, 24.0 * d_link, 300.0)
    s_2_max = min(d_eff / 2.0, 300.0)

    l_dh_avail = min(w_sup_L, w_sup_R) - cover
    l_dh_req = calc_ldh_hook(d_bot, fy, fc, side_cover_mm=cover, tail_cover_mm=cover)

    # 4. 2D Drafting
    draft = Drafting2D()
    draft.add_rectangle(0.0, 0.0, L_tot, h, layer="CONCRETE_OUTLINE")
    draft.add_hidden_rectangle(0.0, -300.0, w_sup_L, 300.0, layer="CONCRETE_HIDDEN")
    draft.add_hidden_rectangle(w_sup_L + L_clr, -300.0, w_sup_R, 300.0, layer="CONCRETE_HIDDEN")

    z_bot_2d = cover + d_link + d_bot / 2.0
    z_top_2d = h - cover - d_link - d_top / 2.0
    draft.add_hooked_rebar_polyline(
        [(cover, z_bot_2d + h90_bot), (cover, z_bot_2d), (L_tot - cover, z_bot_2d), (L_tot - cover, z_bot_2d + h90_bot)],
        width=d_bot,
        layer="REBAR_MAIN",
    )
    draft.add_hooked_rebar_polyline(
        [(cover, z_top_2d - h90_top), (cover, z_top_2d), (L_tot - cover, z_top_2d), (L_tot - cover, z_top_2d - h90_top)],
        width=d_top,
        layer="REBAR_SECONDARY",
    )
    for sx in stirrups["end_positions_mm"] + stirrups["mid_positions_mm"]:
        draft.add_line((w_sup_L + sx, cover), (w_sup_L + sx, h - cover), layer="REBAR_LINKS")

    draft.add_linear_dim((0.0, -180.0), (w_sup_L, 0.0), (w_sup_L + L_clr, 0.0), angle=0.0, text_height=45.0)
    draft.add_text_note(f"{mark} ELEVATION (METRIC - mm)", (0.0, h + 150.0), height=60.0)
    draft.draw_bbs_table((0.0, -520.0), bbs_res["rows"])

    dxf_path, png2d_path = draft.export_dxf_and_png(out / "rc_beam.dxf", out / "rc_beam_2d.png")

    # 5. 3D B-Rep Assembly
    builder = Solid3DBuilder()
    beam_brep = builder.create_box((0.0, -b / 2.0, 0.0), L_tot, b, h)
    builder.assert_valid(beam_brep)

    prim_breps: dict[str, Any] = {f"/World/{mark}/Concrete/BeamBody": beam_brep}
    render_parts: list[dict[str, Any]] = [
        {"brep": beam_brep, "color": "#94a3b8", "opacity": 0.25, "show_edges": True}
    ]
    rebar_breps: list[Any] = []

    for idx, yp in enumerate(bot_dist["positions_mm"]):
        y_c = -b / 2.0 + yp
        bar = builder.create_bar_3d((cover, y_c, z_bot_2d), (L_tot - cover, y_c, z_bot_2d), d_bot / 2.0)
        rebar_breps.append(bar)
        prim_breps[f"/World/{mark}/RebarCage/B1_{idx:02d}"] = bar
        render_parts.append({"brep": bar, "color": "#ef4444", "opacity": 1.0, "metallic": 0.6})

    for idx, yp in enumerate(top_dist["positions_mm"]):
        y_c = -b / 2.0 + yp
        bar = builder.create_bar_3d((cover, y_c, z_top_2d), (L_tot - cover, y_c, z_top_2d), d_top / 2.0)
        rebar_breps.append(bar)
        prim_breps[f"/World/{mark}/RebarCage/T1_{idx:02d}"] = bar
        render_parts.append({"brep": bar, "color": "#22c55e", "opacity": 1.0, "metallic": 0.6})

    clash_res = builder.check_clearance_and_clashes([beam_brep], rebar_breps, cover_mm=cover)
    usd_path = builder.export_assembly_usd(prim_breps, out / "rc_beam.usd")

    render_paths: dict[str, Path] = {}
    if render_3d:
        render_paths = Renderer3D().render_assembly_views(render_parts, out / "renders", prefix="rc_beam", chord_height_tolerance=0.25)

    metrics = {
        "d_eff_mm": round(d_eff, 1),
        "s_clear_mm": bot_dist["s_clear_mm"],
        "s_clear_min_mm": 25.0,
        "s_c2c_mm": bot_dist["s_c2c_mm"],
        "rho": round(rho, 5),
        "rho_min": round(rho_min, 5),
        "A_s_prov_mm2": round(A_s_bot, 1),
        "A_s_min_mm2": round(rho_min * b * d_eff, 1),
        "s_1_act_mm": stirrups["s_1_act_mm"],
        "s_2_act_mm": stirrups["s_2_act_mm"] if stirrups["n_mid"] > 0 else stirrups["s_1_act_mm"],
        "s_1_max_seis_mm": round(s_1_max_seis, 1),
        "s_2_max_mm": round(s_2_max, 1),
        "l_dh_avail_mm": round(l_dh_avail, 1),
        "l_dh_req_mm": round(l_dh_req, 1),
        "H_90_mm": h90_bot,
        "h_minus_2c_mm": h - 2.0 * cover,
        "rebar_to_rebar_overlap_vol": clash_res["rebar_to_rebar_overlap_vol"],
        "min_cover_brep": clash_res["min_cover_brep"],
        "cover_req_mm": cover,
    }
    compliance = evaluate_rules("rc_beam", params, metrics)

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
        f"[RC Beam] DOF={summary['sketch_dof']} | Conc={summary['takeoff']['structural_concrete_m3']:.3f} m3 | "
        f"Steel={summary['total_steel_mass_kg']:.2f} kg | Status={summary['compliance']['status']}"
    )


if __name__ == "__main__":
    main()
