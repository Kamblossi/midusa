"""Template 3: Parametric SI Metric RC Column (rc_column)."""

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
from engine.member_profiles import solve_rect_profile
from engine.rebar_detailing import (
    build_bbs_table,
    calc_lsc_compression_lap,
    compute_takeoff,
    distribute_discrete_bars,
    distribute_multi_zone,
)
from engine.renderer import Renderer3D
from engine.solid_3d import Solid3DBuilder
from rules.validator import evaluate_rules


def _rect_perimeter_bar_coords(b: float, h: float, cover: float, d_tie: float, d_vert: float, n_bars: int) -> list[tuple[float, float]]:
    """Compute centered (x, y) coordinates of rectangular column vertical bars."""
    x_min = -b / 2.0 + cover + d_tie + d_vert / 2.0
    x_max = b / 2.0 - cover - d_tie - d_vert / 2.0
    y_min = -h / 2.0 + cover + d_tie + d_vert / 2.0
    y_max = h / 2.0 - cover - d_tie - d_vert / 2.0
    pts = [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]
    if n_bars >= 8:
        pts.extend([(0.0, y_min), (x_max, 0.0), (0.0, y_max), (x_min, 0.0)])
    return pts[:n_bars]


def build(params: dict[str, Any], out_dir: str | Path, render_3d: bool = True) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    mark = str(params.get("member_mark", "C-01"))
    b = float(params["width_mm"])
    h = float(params["depth_mm"])
    H_clr = float(params["clear_height_mm"])
    cover = float(params["cover_mm"])
    n_vert = int(params["vert_bar_count"])
    d_vert = float(params["vert_bar_dia_mm"])
    lap_proj = float(params["lap_projection_mm"])
    d_tie = float(params["tie_dia_mm"])
    l_o = float(params.get("confinement_len_mm", 0.0))
    s_conf = float(params["tie_conf_spacing_mm"])
    s_mid = float(params["tie_mid_spacing_mm"])
    has_crossties = bool(params.get("has_crossties", False))
    fc = float(params["fc_mpa"])
    fy = float(params["fy_mpa"])

    # 1. Primitive 1: PlaneGCS DOF == 0 profile
    prof = solve_rect_profile(b, h, H_clr, clear_span_mm=H_clr, is_column=True)

    # 2. Primitive 2 & 3: Tie distribution & BBS
    ties = distribute_multi_zone(H_clr, l_o, s_conf, s_mid, d_tie, c_end_mm=50.0)
    n_ties_tot = ties["n_end_total"] + ties["n_mid"]

    a_tie = b - 2.0 * cover
    b_tie = h - 2.0 * cover
    v1_len = H_clr + lap_proj

    bbs_items: list[dict[str, Any]] = [
        {
            "bar_mark": "V1",
            "member_mark": mark,
            "grade_prefix": "T",
            "dia_mm": d_vert,
            "spacing_mm": None,
            "num_members": 1,
            "bars_per_member": n_vert,
            "shape_code": "00",
            "bend_dims_mm": {"A": v1_len},
        },
        {
            "bar_mark": "L1",
            "member_mark": mark,
            "grade_prefix": "R",
            "dia_mm": d_tie,
            "spacing_mm": ties["s_1_act_mm"],
            "num_members": 1,
            "bars_per_member": n_ties_tot,
            "shape_code": "51",
            "bend_dims_mm": {"A": a_tie, "B": b_tie},
            "is_link": True,
        },
    ]
    if has_crossties:
        bbs_items.append(
            {
                "bar_mark": "L2",
                "member_mark": mark,
                "grade_prefix": "R",
                "dia_mm": d_tie,
                "spacing_mm": ties["s_1_act_mm"],
                "num_members": 1,
                "bars_per_member": 2 * n_ties_tot,
                "shape_code": "CT",
                "bend_dims_mm": {"A": a_tie},
                "is_link": True,
            }
        )

    bbs_res = build_bbs_table(bbs_items)
    takeoff = compute_takeoff(prof["volume_m3"], 0.0, prof["formwork_m2"], bbs_res["total_steel_kg"])

    # 3. Structural checks
    A_s_vert = n_vert * (math.pi * d_vert ** 2 / 4.0)
    rho_g = A_s_vert / (b * h)
    bars_per_face = 3 if n_vert >= 8 else 2
    face_dist = distribute_discrete_bars(b, cover, d_tie, d_vert, bars_per_face)
    s_clr_face = face_dist["s_clear_mm"]
    l_sc = calc_lsc_compression_lap(d_vert, fy, fc)
    s_conf_max = min(8.0 * d_vert, 24.0 * d_tie, min(b, h) / 2.0, 300.0)
    s_mid_max = min(16.0 * d_vert, 48.0 * d_tie, min(b, h))

    # 4. 2D Drafting
    draft = Drafting2D()
    draft.add_rectangle(-b / 2.0, 0.0, b, H_clr, layer="CONCRETE_OUTLINE")
    bar_coords = _rect_perimeter_bar_coords(b, h, cover, d_tie, d_vert, n_vert)
    for bx, _ in sorted(set((round(p[0], 2), 0.0) for p in bar_coords)):
        draft.add_line((bx, 0.0), (bx, H_clr + lap_proj), layer="REBAR_MAIN")
    for tz in ties["end_positions_mm"] + ties["mid_positions_mm"]:
        draft.add_line((-b / 2.0 + cover, tz), (b / 2.0 - cover, tz), layer="REBAR_LINKS")
    draft.add_linear_dim((-b / 2.0 - 200.0, 0.0), (-b / 2.0, 0.0), (-b / 2.0, H_clr), angle=90.0, text_height=50.0)
    draft.add_text_note(f"{mark} ELEVATION (METRIC - mm)", (-b / 2.0, H_clr + lap_proj + 120.0), height=60.0)
    draft.draw_bbs_table((b / 2.0 + 400.0, H_clr), bbs_res["rows"])

    dxf_path, png2d_path = draft.export_dxf_and_png(out / "rc_column.dxf", out / "rc_column_2d.png")

    # 5. 3D B-Rep Assembly
    builder = Solid3DBuilder()
    col_brep = builder.create_box((-b / 2.0, -h / 2.0, 0.0), b, h, H_clr)
    builder.assert_valid(col_brep)
    prim_breps: dict[str, Any] = {f"/World/{mark}/Concrete/ColumnShaft": col_brep}
    render_parts: list[dict[str, Any]] = [
        {"brep": col_brep, "color": "#94a3b8", "opacity": 0.25, "show_edges": True}
    ]
    rebar_breps: list[Any] = []
    for idx, (bx, by) in enumerate(bar_coords):
        bar = builder.create_bar_3d((bx, by, 0.0), (bx, by, H_clr + lap_proj), d_vert / 2.0)
        rebar_breps.append(bar)
        prim_breps[f"/World/{mark}/RebarCage/V1_{idx:02d}"] = bar
        render_parts.append({"brep": bar, "color": "#ef4444", "opacity": 1.0, "metallic": 0.6})

    clash_res = builder.check_clearance_and_clashes([col_brep], rebar_breps, cover_mm=cover)
    usd_path = builder.export_assembly_usd(prim_breps, out / "rc_column.usd")

    render_paths: dict[str, Path] = {}
    if render_3d:
        render_paths = Renderer3D().render_assembly_views(render_parts, out / "renders", prefix="rc_column", chord_height_tolerance=0.25)

    metrics = {
        "rho_g": round(rho_g, 4),
        "s_clr_face_mm": round(s_clr_face, 1),
        "s_c2c_face_mm": round(face_dist["s_c2c_mm"], 1),
        "n_ties_end": ties["n_end_total"],
        "n_ties_mid": ties["n_mid"],
        "n_ties_total": n_ties_tot,
        "n_crossties": 2 * n_ties_tot if has_crossties else 0,
        "s_conf_act_mm": ties["s_1_act_mm"],
        "s_mid_act_mm": ties["s_2_act_mm"],
        "s_conf_max_mm": round(s_conf_max, 1),
        "s_mid_max_mm": round(s_mid_max, 1),
        "l_sc_mm": round(l_sc, 1),
        "s_clear_mm": s_clr_face,
        "s_clear_min_mm": 25.0,
        "rebar_to_rebar_overlap_vol": clash_res["rebar_to_rebar_overlap_vol"],
        "min_cover_brep": clash_res["min_cover_brep"],
        "cover_req_mm": cover,
    }
    compliance = evaluate_rules("rc_column", params, metrics)

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
        f"[RC Column] DOF={summary['sketch_dof']} | Conc={summary['takeoff']['structural_concrete_m3']:.3f} m3 | "
        f"Steel={summary['total_steel_mass_kg']:.2f} kg | Status={summary['compliance']['status']}"
    )


if __name__ == "__main__":
    main()
