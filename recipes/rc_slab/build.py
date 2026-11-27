"""Template 4: Parametric SI Metric RC Slab (rc_slab)."""

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
from engine.member_profiles import solve_slab_profile
from engine.rebar_detailing import build_bbs_table, compute_takeoff, distribute_bars
from engine.renderer import Renderer3D
from engine.solid_3d import Solid3DBuilder
from rules.validator import evaluate_rules


def build(params: dict[str, Any], out_dir: str | Path, render_3d: bool = True) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    mark = str(params.get("member_mark", "S-01"))
    lx = float(params["length_x_mm"])
    ly = float(params["length_y_mm"])
    h = float(params["thickness_mm"])
    cov_top = float(params["cover_top_mm"])
    cov_bot = float(params["cover_bot_mm"])
    c_edge = float(params.get("first_bar_edge_offset_mm", 50.0))

    d_b1 = float(params["b1_dia_mm"])
    s_b1 = float(params["b1_spacing_mm"])
    d_b2 = float(params["b2_dia_mm"])
    s_b2 = float(params["b2_spacing_mm"])
    has_top = bool(params.get("has_top_strips", False))
    d_t1 = float(params.get("t1_dia_mm", 10.0))
    s_t1 = float(params.get("t1_spacing_mm", 200.0))
    t1_ratio = float(params.get("t1_extension_ratio", 0.25))
    fy = float(params.get("fy_mpa", 460.0))

    # 1. Primitive 1: PlaneGCS DOF == 0 profile
    prof = solve_slab_profile(lx, ly, h)

    # 2. Primitive 2 & 3: Rebar distributions & BBS
    # B1 runs along short span (Y), distributed along X
    dist_b1 = distribute_bars(lx, c_edge, d_b1, s_b1)
    # B2 runs along long span (X), distributed along Y
    dist_b2 = distribute_bars(ly, c_edge, d_b2, s_b2)

    len_b1 = ly - 2.0 * cov_bot
    len_b2 = lx - 2.0 * cov_bot

    bbs_items: list[dict[str, Any]] = [
        {
            "bar_mark": "B1",
            "member_mark": mark,
            "grade_prefix": "T",
            "dia_mm": d_b1,
            "spacing_mm": dist_b1["actual_spacing_mm"],
            "num_members": 1,
            "bars_per_member": dist_b1["bar_count"],
            "shape_code": "00",
            "bend_dims_mm": {"A": len_b1},
        },
        {
            "bar_mark": "B2",
            "member_mark": mark,
            "grade_prefix": "T",
            "dia_mm": d_b2,
            "spacing_mm": dist_b2["actual_spacing_mm"],
            "num_members": 1,
            "bars_per_member": dist_b2["bar_count"],
            "shape_code": "00",
            "bend_dims_mm": {"A": len_b2},
        },
    ]

    n_t1a = 0
    n_t1b = 0
    if has_top:
        l_short = min(lx, ly)
        t1_proj = t1_ratio * l_short - cov_top
        t1_leg = h - cov_top - cov_bot
        dist_t1a = distribute_bars(lx, c_edge, d_t1, s_t1)
        dist_t1b = distribute_bars(ly, c_edge, d_t1, s_t1)
        n_t1a = 2 * dist_t1a["bar_count"]
        n_t1b = 2 * dist_t1b["bar_count"]
        bbs_items.extend(
            [
                {
                    "bar_mark": "T1a",
                    "member_mark": mark,
                    "grade_prefix": "T",
                    "dia_mm": d_t1,
                    "spacing_mm": dist_t1a["actual_spacing_mm"],
                    "num_members": 1,
                    "bars_per_member": n_t1a,
                    "shape_code": "11",
                    "bend_dims_mm": {"A": t1_proj, "B": t1_leg},
                },
                {
                    "bar_mark": "T1b",
                    "member_mark": mark,
                    "grade_prefix": "T",
                    "dia_mm": d_t1,
                    "spacing_mm": dist_t1b["actual_spacing_mm"],
                    "num_members": 1,
                    "bars_per_member": n_t1b,
                    "shape_code": "11",
                    "bend_dims_mm": {"A": t1_proj, "B": t1_leg},
                },
            ]
        )

    bbs_res = build_bbs_table(bbs_items)
    takeoff = compute_takeoff(prof["volume_m3"], 0.0, prof["formwork_m2"], bbs_res["total_steel_kg"])

    # 3. Structural checks
    rho_min = max(0.0018 * 420.0 / fy, 0.0014)
    as_min_pm = rho_min * 1000.0 * h
    as_b1_pm = (math.pi * d_b1 ** 2 / 4.0) * (1000.0 / dist_b1["actual_spacing_mm"])
    as_b2_pm = (math.pi * d_b2 ** 2 / 4.0) * (1000.0 / dist_b2["actual_spacing_mm"])

    # 4. 2D Drafting
    draft = Drafting2D()
    draft.add_rectangle(0.0, 0.0, lx, ly, layer="CONCRETE_OUTLINE")
    for px in dist_b1["positions_mm"][:6]:
        draft.add_line((px, cov_bot), (px, ly - cov_bot), layer="REBAR_MAIN")
    for py in dist_b2["positions_mm"][:6]:
        draft.add_line((cov_bot, py), (lx - cov_bot, py), layer="REBAR_SECONDARY")
    draft.add_linear_dim((0.0, -250.0), (0.0, 0.0), (lx, 0.0), angle=0.0, text_height=60.0)
    draft.add_linear_dim((-250.0, 0.0), (0.0, 0.0), (0.0, ly), angle=90.0, text_height=60.0)
    draft.add_text_note(f"{mark} SLAB PLAN (METRIC - mm)", (0.0, ly + 150.0), height=75.0)
    draft.draw_bbs_table((lx + 400.0, ly), bbs_res["rows"])

    dxf_path, png2d_path = draft.export_dxf_and_png(out / "rc_slab.dxf", out / "rc_slab_2d.png")

    # 5. 3D B-Rep Assembly
    builder = Solid3DBuilder()
    slab_brep = builder.create_box((0.0, 0.0, 0.0), lx, ly, h)
    builder.assert_valid(slab_brep)

    prim_breps: dict[str, Any] = {f"/World/{mark}/Concrete/SlabPanel": slab_brep}
    render_parts: list[dict[str, Any]] = [
        {"brep": slab_brep, "color": "#94a3b8", "opacity": 0.25, "show_edges": True}
    ]
    rebar_breps: list[Any] = []

    z_b1 = cov_bot + d_b1 / 2.0
    for idx, px in enumerate(dist_b1["positions_mm"]):
        bar = builder.create_bar_3d((px, cov_bot, z_b1), (px, ly - cov_bot, z_b1), d_b1 / 2.0)
        rebar_breps.append(bar)
        prim_breps[f"/World/{mark}/RebarCage/B1_{idx:02d}"] = bar
        render_parts.append({"brep": bar, "color": "#ef4444", "opacity": 1.0, "metallic": 0.6})

    z_b2 = cov_bot + d_b1 + d_b2 / 2.0 + 0.5
    for idx, py in enumerate(dist_b2["positions_mm"]):
        bar = builder.create_bar_3d((cov_bot, py, z_b2), (lx - cov_bot, py, z_b2), d_b2 / 2.0)
        rebar_breps.append(bar)
        prim_breps[f"/World/{mark}/RebarCage/B2_{idx:02d}"] = bar
        render_parts.append({"brep": bar, "color": "#22c55e", "opacity": 1.0, "metallic": 0.6})

    clash_res = builder.check_clearance_and_clashes([slab_brep], rebar_breps, cover_mm=cov_bot)
    usd_path = builder.export_assembly_usd(prim_breps, out / "rc_slab.usd")

    render_paths: dict[str, Path] = {}
    if render_3d:
        render_paths = Renderer3D().render_assembly_views(render_parts, out / "renders", prefix="rc_slab", chord_height_tolerance=0.4)

    metrics = {
        "n_b1": dist_b1["bar_count"],
        "n_b2": dist_b2["bar_count"],
        "n_t1": n_t1a + n_t1b,
        "n_t1a": n_t1a,
        "n_t1b": n_t1b,
        "s_b1_act_mm": dist_b1["actual_spacing_mm"],
        "s_b2_act_mm": dist_b2["actual_spacing_mm"],
        "A_s_min_pm_prov_mm2": round(min(as_b1_pm, as_b2_pm), 1),
        "A_s_min_pm_req_mm2": round(as_min_pm, 1),
        "rebar_to_rebar_overlap_vol": clash_res["rebar_to_rebar_overlap_vol"],
        "min_cover_brep": clash_res["min_cover_brep"],
        "cover_req_mm": cov_bot,
    }
    compliance = evaluate_rules("rc_slab", params, metrics)

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
        f"[RC Slab] DOF={summary['sketch_dof']} | Conc={summary['takeoff']['structural_concrete_m3']:.3f} m3 | "
        f"Steel={summary['total_steel_mass_kg']:.2f} kg | Status={summary['compliance']['status']}"
    )


if __name__ == "__main__":
    main()
