"""Template 5B: Composable Building Layout and Roof Framing Spec (layout_roof_spec)."""

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
from engine.member_profiles import solve_pad_footing_profile, solve_rect_profile, solve_slab_profile
from engine.renderer import Renderer3D
from engine.solid_3d import Solid3DBuilder


def build(params: dict[str, Any], out_dir: str | Path, render_3d: bool = True) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    x_bays = [float(x) for x in params["x_bays_mm"]]
    y_bays = [float(y) for y in params["y_bays_mm"]]
    story_h = float(params["story_height_mm"])

    pad_ref = params["pad_ref"]
    col_ref = params["col_ref"]
    beam_ref = params["beam_ref"]
    slab_ref = params["slab_ref"]

    pad_w = float(pad_ref["pad_width_mm"])
    pad_l = float(pad_ref["pad_length_mm"])
    pad_d = float(pad_ref["pad_depth_mm"])
    t_b = float(pad_ref.get("blinding_thickness_mm", 50.0))
    p_b = float(pad_ref.get("blinding_projection_mm", 50.0))

    col_w = float(col_ref["width_mm"])
    col_d = float(col_ref["depth_mm"])
    beam_w = float(beam_ref["width_mm"])
    beam_h = float(beam_ref["depth_mm"])
    slab_h = float(slab_ref["thickness_mm"])

    # Grid coordinates
    x_grids = [0.0]
    for bx in x_bays:
        x_grids.append(x_grids[-1] + bx)
    y_grids = [0.0]
    for by in y_bays:
        y_grids.append(y_grids[-1] + by)

    nx, ny = len(x_bays), len(y_bays)
    n_nodes = (nx + 1) * (ny + 1)

    # 1. Primitive 1 Volumes (Non-overlapping partitioned frame)
    pad_prof = solve_pad_footing_profile(pad_w, pad_l, pad_d, t_b_mm=t_b, p_b_mm=p_b)
    col_prof = solve_rect_profile(col_w, col_d, story_h, clear_span_mm=story_h, is_column=True)
    joint_prof = solve_rect_profile(col_w, col_d, beam_h, clear_span_mm=beam_h, is_column=True)

    v_pads = n_nodes * pad_prof["volume_m3"]
    v_blind = n_nodes * pad_prof["blinding_m3"]
    v_cols = n_nodes * col_prof["volume_m3"]
    v_joints = n_nodes * joint_prof["volume_m3"]

    v_xbeams = 0.0
    for bx in x_bays:
        clr = bx - col_w
        v_xbeams += (ny + 1) * solve_rect_profile(beam_w, beam_h, clr, clear_span_mm=clr)["volume_m3"]

    v_ybeams = 0.0
    for by in y_bays:
        clr = by - col_d
        v_ybeams += (nx + 1) * solve_rect_profile(beam_w, beam_h, clr, clear_span_mm=clr)["volume_m3"]

    v_slabs = 0.0
    for bx in x_bays:
        for by in y_bays:
            v_slabs += solve_slab_profile(bx - col_w, by - col_d, slab_h)["volume_m3"]

    total_frame_conc = round(v_pads + v_cols + v_xbeams + v_ybeams + v_joints + v_slabs, 3)

    # 2. Roof Geometry & Framing
    roof_type = str(params["roof_type"]).upper()
    alpha_rad = math.radians(float(params["pitch_deg"]))
    S_roof = float(params["clear_span_mm"])
    L_eave = float(params["eaves_overhang_mm"])
    overhang_off = float(params.get("overhang_offset_mm", 0.0))
    truss_spc = float(params["truss_spacing_mm"])
    purlin_spc = float(params["purlin_spacing_mm"])

    if roof_type in {"GABLE", "HIP"}:
        H_ridge = (S_roof / 2.0 + overhang_off) * math.tan(alpha_rad)
        eaves_drop = L_eave * math.tan(alpha_rad)
        L_rafter = (S_roof / 2.0 + L_eave) / math.cos(alpha_rad)
    else:
        H_ridge = (S_roof + overhang_off) * math.tan(alpha_rad)
        eaves_drop = L_eave * math.tan(alpha_rad)
        L_rafter = (S_roof + 2.0 * L_eave) / math.cos(alpha_rad)

    L_x_tot = sum(x_bays)
    n_main_trusses = math.ceil(L_x_tot / truss_spc) + 1
    n_truss_assemblies = n_main_trusses + 2  # + 2 verge ladder overhangs
    n_purlins_per_slope = math.ceil(L_rafter / purlin_spc) + 1
    n_purlin_lines = 2 * n_purlins_per_slope if roof_type in {"GABLE", "HIP"} else n_purlins_per_slope
    purlin_length_each_m = (L_x_tot + 2.0 * L_eave) / 1000.0
    total_purlin_run_m = n_purlin_lines * purlin_length_each_m

    # 3. 2D Framing Plan
    draft = Drafting2D()
    for xg in x_grids:
        draft.add_line((xg, -1000.0), (xg, y_grids[-1] + 1000.0), layer="GRIDLINES")
        for yg in y_grids:
            draft.add_rectangle(xg - pad_w / 2.0, yg - pad_l / 2.0, pad_w, pad_l, layer="CONCRETE_HIDDEN")
            draft.add_rectangle(xg - col_w / 2.0, yg - col_d / 2.0, col_w, col_d, layer="CONCRETE_OUTLINE")
    for yg in y_grids:
        draft.add_line((-1000.0, yg), (x_grids[-1] + 1000.0, yg), layer="GRIDLINES")
    draft.add_text_note("STRUCTURAL FRAMING PLAN (METRIC - mm)", (0.0, y_grids[-1] + 1200.0), height=140.0)
    dxf_path, png2d_path = draft.export_dxf_and_png(out / "layout_roof.dxf", out / "layout_roof_2d.png")

    # 4. 3D Building Frame Assembly
    builder = Solid3DBuilder()
    prim_breps: dict[str, Any] = {}
    render_parts: list[dict[str, Any]] = []
    z_beam_bot = pad_d + story_h
    for ix, xg in enumerate(x_grids):
        for iy, yg in enumerate(y_grids):
            pf = builder.create_box((xg - pad_w / 2.0, yg - pad_l / 2.0, 0.0), pad_w, pad_l, pad_d)
            col = builder.create_box((xg - col_w / 2.0, yg - col_d / 2.0, pad_d), col_w, col_d, story_h + beam_h)
            prim_breps[f"/World/BuildingFrame/Footings/PF_{ix}_{iy}"] = pf
            prim_breps[f"/World/BuildingFrame/Columns/C_{ix}_{iy}"] = col
            render_parts.append({"brep": pf, "color": "#64748b", "opacity": 0.45, "show_edges": True})
            render_parts.append({"brep": col, "color": "#94a3b8", "opacity": 0.55, "show_edges": True})

    for ix, bx in enumerate(x_bays):
        for iy, yg in enumerate(y_grids):
            xb = builder.create_box((x_grids[ix] + col_w / 2.0, yg - beam_w / 2.0, z_beam_bot), bx - col_w, beam_w, beam_h)
            prim_breps[f"/World/BuildingFrame/Beams/BX_{ix}_{iy}"] = xb
            render_parts.append({"brep": xb, "color": "#cbd5e1", "opacity": 0.5, "show_edges": True})

    for ix, xg in enumerate(x_grids):
        for iy, by in enumerate(y_bays):
            yb = builder.create_box((xg - beam_w / 2.0, y_grids[iy] + col_d / 2.0, z_beam_bot), beam_w, by - col_d, beam_h)
            prim_breps[f"/World/BuildingFrame/Beams/BY_{ix}_{iy}"] = yb
            render_parts.append({"brep": yb, "color": "#cbd5e1", "opacity": 0.5, "show_edges": True})

    usd_path = builder.export_assembly_usd(prim_breps, out / "layout_roof.usd")
    render_paths: dict[str, Path] = {}
    if render_3d:
        render_paths = Renderer3D().render_assembly_views(render_parts, out / "renders", prefix="layout_roof", chord_height_tolerance=1.0)

    summary = {
        "sketch_dof": 0,
        "concrete_volumes_m3": {
            "pads": round(v_pads, 3),
            "blinding": round(v_blind, 3),
            "columns": round(v_cols, 3),
            "x_beams": round(v_xbeams, 3),
            "y_beams": round(v_ybeams, 3),
            "joint_cores": round(v_joints, 3),
            "slabs": round(v_slabs, 3),
            "total_frame_structural": total_frame_conc,
        },
        "roof": {
            "H_ridge_mm": round(H_ridge, 1),
            "eaves_drop_mm": round(eaves_drop, 1),
            "L_rafter_mm": round(L_rafter, 1),
            "n_truss_assemblies": n_truss_assemblies,
            "n_purlin_lines": n_purlin_lines,
            "total_purlin_run_m": round(total_purlin_run_m, 2),
        },
        "outputs": {"dxf": str(dxf_path), "png_2d": str(png2d_path), "usd": str(usd_path), "renders": {k: str(v) for k, v in render_paths.items()}},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    ws = Path(__file__).resolve().parent
    params = json.loads((ws / "params.json").read_text(encoding="utf-8"))
    summary = build(params, ws)
    print(
        f"[Layout+Roof] Frame Conc={summary['concrete_volumes_m3']['total_frame_structural']:.3f} m3 | "
        f"H_ridge={summary['roof']['H_ridge_mm']} mm | L_rafter={summary['roof']['L_rafter_mm']} mm"
    )


if __name__ == "__main__":
    main()
