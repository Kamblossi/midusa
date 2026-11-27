"""Parametric RC Pad Footing recipe (SI metric: mm, m, MPa, kg)."""

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
from engine.rebar_detailing import (
    BarScheduleItem,
    build_bar_bending_schedule,
    compute_bar_distribution,
    standard_hook_extension_mm,
    total_schedule_mass_kg,
)
from engine.renderer import Renderer3D
from engine.sketch_bridge import SketchBridge
from engine.solid_3d import Solid3DBuilder


def _dowel_xy_positions(
    col_x0: float,
    col_y0: float,
    col_w: float,
    col_d: float,
    col_cover: float,
    dowel_count: int,
) -> list[tuple[float, float]]:
    """Compute starter dowel (x, y) coordinates inside the column perimeter."""
    x_min = col_x0 + col_cover
    x_max = col_x0 + col_w - col_cover
    y_min = col_y0 + col_cover
    y_max = col_y0 + col_d - col_cover
    x_mid = 0.5 * (x_min + x_max)
    y_mid = 0.5 * (y_min + y_max)

    corners = [
        (x_min, y_min),
        (x_max, y_min),
        (x_max, y_max),
        (x_min, y_max),
    ]
    if dowel_count == 4:
        return corners
    if dowel_count == 8:
        return corners + [
            (x_mid, y_min),
            (x_max, y_mid),
            (x_mid, y_max),
            (x_min, y_mid),
        ]

    # General fallback: distribute evenly around perimeter
    pts: list[tuple[float, float]] = list(corners)
    extra = max(0, dowel_count - 4)
    for i in range(extra):
        t = (i + 1) / (extra + 1)
        pts.append((x_min + t * (x_max - x_min), y_min if i % 2 == 0 else y_max))
    return pts[:dowel_count]


def build(params: dict[str, Any], out_dir: str | Path) -> dict[str, Any]:
    """Generate 2D DXF/PNG, metric BBS, 3D USD assembly, and multi-angle PyVista renders."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    w = float(params["footing_width_mm"])
    l = float(params["footing_length_mm"])
    d = float(params["footing_depth_mm"])
    t_blind = float(params["blinding_thickness_mm"])
    col_w = float(params["col_width_mm"])
    col_d = float(params["col_depth_mm"])
    stub_h = float(params["col_stub_height_mm"])
    cover = float(params["cover_mm"])

    bot_dia = float(params["bottom_bar_dia_mm"])
    bot_spc = float(params["bottom_bar_spacing_mm"])
    dowel_n = int(params["dowel_count"])
    dowel_dia = float(params["dowel_bar_dia_mm"])
    dowel_proj = float(params["dowel_projection_mm"])
    link_dia = float(params["link_bar_dia_mm"])
    link_spc = float(params["link_spacing_mm"])

    fc_foot = float(params["fc_footing_mpa"])
    fc_col = float(params["fc_column_mpa"])
    fy = float(params["fy_mpa"])

    blinding_proj = 50.0
    col_cover = 40.0

    # 1. Solve 2D Plan Geometry with PlaneGCS (DOF == 0)
    sketch = SketchBridge()
    sketch.add_rectangle("pad", 0.0, 0.0, w, l, fix_origin=True)
    col_x0 = (w - col_w) / 2.0
    col_y0 = (l - col_d) / 2.0
    sketch.add_rectangle("col", col_x0, col_y0, col_w, col_d, fix_origin=True)
    solved = sketch.solve(require_zero_dof=True)

    # 2. Compute Metric Rebar Distributions & Bar Bending Schedule (ACI 315-99)
    dist_x = compute_bar_distribution(l, cover, bot_dia, bot_spc)  # bars running along X, distributed along Y
    dist_y = compute_bar_distribution(w, cover, bot_dia, bot_spc)  # bars running along Y, distributed along X

    x_bar_len = dist_y["out_to_out_length_mm"]
    y_bar_len = dist_x["out_to_out_length_mm"]
    bot_hook = standard_hook_extension_mm(bot_dia, angle_deg=90)
    dowel_hook = standard_hook_extension_mm(dowel_dia, angle_deg=90)
    dowel_vert_len = (d - cover - 2.0 * bot_dia) + dowel_proj

    link_x_leg = col_w - 2.0 * col_cover
    link_y_leg = col_d - 2.0 * col_cover
    link_hook = standard_hook_extension_mm(link_dia, angle_deg=135, is_tie_or_stirrup=True)
    link_count = max(2, math.floor((d + stub_h - cover) / link_spc) + 1)

    bbs_items = [
        BarScheduleItem(
            mark="01",
            bar_type="T",
            bar_dia_mm=bot_dia,
            no_off=dist_x["bar_count"],
            spacing_mm=bot_spc,
            shape_code="21",
            legs_mm=(x_bar_len, bot_hook, bot_hook),
            bend_count=2,
        ),
        BarScheduleItem(
            mark="02",
            bar_type="T",
            bar_dia_mm=bot_dia,
            no_off=dist_y["bar_count"],
            spacing_mm=bot_spc,
            shape_code="21",
            legs_mm=(y_bar_len, bot_hook, bot_hook),
            bend_count=2,
        ),
        BarScheduleItem(
            mark="03",
            bar_type="T",
            bar_dia_mm=dowel_dia,
            no_off=dowel_n,
            spacing_mm=None,
            shape_code="11",
            legs_mm=(dowel_vert_len, dowel_hook),
            bend_count=1,
        ),
        BarScheduleItem(
            mark="04",
            bar_type="R",
            bar_dia_mm=link_dia,
            no_off=link_count,
            spacing_mm=link_spc,
            shape_code="51",
            legs_mm=(link_x_leg, link_y_leg, link_x_leg, link_y_leg, link_hook, link_hook),
            is_tie_or_stirrup=True,
            bend_count=5,
        ),
    ]
    bbs_rows = build_bar_bending_schedule(bbs_items)
    total_steel_kg = total_schedule_mass_kg(bbs_rows)

    dowel_pts = _dowel_xy_positions(col_x0, col_y0, col_w, col_d, col_cover, dowel_n)

    # 3. Generate 2D DXF & PNG (Plan View + Section A-A + Metric BBS Table)
    draft = Drafting2D()

    # Plan View
    draft.add_rectangle(
        -blinding_proj,
        -blinding_proj,
        w + 2.0 * blinding_proj,
        l + 2.0 * blinding_proj,
        layer="BLINDING",
    )
    draft.add_rectangle(0.0, 0.0, w, l, layer="CONCRETE_OUTLINE")
    draft.add_rectangle(col_x0, col_y0, col_w, col_d, layer="CONCRETE_OUTLINE")

    # Bottom rebar grid in plan
    for py in dist_x["positions_mm"]:
        draft.add_line((cover, py), (w - cover, py), layer="REBAR_MAIN")
    for px in dist_y["positions_mm"]:
        draft.add_line((px, cover), (px, l - cover), layer="REBAR_MAIN")

    # Dowel circles in plan
    for dx, dy in dowel_pts:
        draft.add_circle(dx, dy, dowel_dia * 0.75, layer="REBAR_DOWELS", with_centerlines=False)

    # Section A-A cut line, North arrow, Plan Dimensions
    draft.add_section_callout((-180.0, l / 2.0), (w + 180.0, l / 2.0), label="A")
    draft.add_north_arrow((w + 350.0, l - 250.0), size=200.0)
    draft.add_linear_dim((0.0, -260.0), (0.0, 0.0), (w, 0.0), angle=0.0, text_height=48.0)
    draft.add_linear_dim((-260.0, 0.0), (0.0, 0.0), (0.0, l), angle=90.0, text_height=48.0)
    draft.add_linear_dim((col_x0, l + 160.0), (col_x0, l), (col_x0 + col_w, l), angle=0.0, text_height=42.0)
    draft.add_text_note("PLAN VIEW (METRIC - mm)", (0.0, l + 260.0), height=65.0)

    # Section A-A (to the right of Plan View)
    sx0 = w + 900.0
    sy0 = 0.0
    # Blinding concrete
    draft.add_rectangle(sx0 - blinding_proj, sy0 - t_blind, w + 2.0 * blinding_proj, t_blind, layer="BLINDING")
    # Pad concrete
    draft.add_rectangle(sx0, sy0, w, d, layer="CONCRETE_OUTLINE")
    draft.add_concrete_hatch([(sx0, sy0), (sx0 + w, sy0), (sx0 + w, sy0 + d), (sx0, sy0 + d)], scale=14.0)
    # Column stub
    scol_x0 = sx0 + col_x0
    draft.add_rectangle(scol_x0, sy0 + d, col_w, stub_h, layer="CONCRETE_OUTLINE")
    draft.add_concrete_hatch(
        [(scol_x0, sy0 + d), (scol_x0 + col_w, sy0 + d), (scol_x0 + col_w, sy0 + d + stub_h), (scol_x0, sy0 + d + stub_h)],
        scale=12.0,
    )

    # Bottom X bar (hooked polyline) in Section A-A
    z_bot_x = sy0 + cover + bot_dia / 2.0
    draft.add_hooked_rebar_polyline(
        [
            (sx0 + cover, z_bot_x + bot_hook),
            (sx0 + cover, z_bot_x),
            (sx0 + w - cover, z_bot_x),
            (sx0 + w - cover, z_bot_x + bot_hook),
        ],
        width=bot_dia,
        layer="REBAR_MAIN",
    )
    # Bottom Y bars (dots/circles)
    z_bot_y = z_bot_x + bot_dia
    for px in dist_y["positions_mm"]:
        draft.add_circle(sx0 + px, z_bot_y, bot_dia / 2.0, layer="REBAR_MAIN", with_centerlines=False)

    # Starter dowels in Section A-A (left & right column faces)
    z_dowel_base = z_bot_y + bot_dia / 2.0
    z_dowel_top = sy0 + d + dowel_proj
    draft.add_hooked_rebar_polyline(
        [
            (scol_x0 + col_cover - dowel_hook, z_dowel_base),
            (scol_x0 + col_cover, z_dowel_base),
            (scol_x0 + col_cover, z_dowel_top),
        ],
        width=dowel_dia,
        layer="REBAR_DOWELS",
    )
    draft.add_hooked_rebar_polyline(
        [
            (scol_x0 + col_w - col_cover + dowel_hook, z_dowel_base),
            (scol_x0 + col_w - col_cover, z_dowel_base),
            (scol_x0 + col_w - col_cover, z_dowel_top),
        ],
        width=dowel_dia,
        layer="REBAR_DOWELS",
    )

    # Column links in Section A-A
    z_link = sy0 + d + 50.0
    while z_link <= sy0 + d + stub_h - 40.0:
        draft.add_line(
            (scol_x0 + col_cover - 10.0, z_link),
            (scol_x0 + col_w - col_cover + 10.0, z_link),
            layer="REBAR_TIES",
        )
        z_link += link_spc

    # Section dimensions & notes
    draft.add_linear_dim((sx0 + w + 180.0, sy0), (sx0 + w, sy0), (sx0 + w, sy0 + d), angle=90.0, text_height=45.0)
    draft.add_linear_dim((sx0 + w + 180.0, sy0 - t_blind), (sx0 + w, sy0 - t_blind), (sx0 + w, sy0), angle=90.0, text_height=38.0)
    draft.add_linear_dim((scol_x0 + col_w + 180.0, sy0 + d), (scol_x0 + col_w, sy0 + d), (scol_x0 + col_w, sy0 + d + stub_h), angle=90.0, text_height=45.0)
    draft.add_text_note("SECTION A-A (METRIC - mm)", (sx0, sy0 + d + stub_h + 150.0), height=65.0)
    draft.add_text_note(
        f"CONCRETE: f'c pad = {fc_foot:.0f} MPa, f'c col = {fc_col:.0f} MPa | STEEL: fy = {fy:.0f} MPa | COVER = {cover:.0f} mm",
        (0.0, -520.0),
        height=45.0,
    )

    # Bar Bending Schedule Table below Plan & Section
    draft.add_bbs_table((0.0, -720.0), bbs_rows)

    dxf_path = draft.save_dxf(out / "pad_footing.dxf")
    png2d_path = draft.export_png(out / "pad_footing_2d.png", dpi=200)

    # 4. Build 3D B-Rep Solids (Concrete + Rebar Cage) & Export Hierarchical USD
    builder = Solid3DBuilder()
    blinding_brep = builder.create_box(
        (-blinding_proj, -blinding_proj, -t_blind),
        w + 2.0 * blinding_proj,
        l + 2.0 * blinding_proj,
        t_blind,
    )
    pad_brep = builder.create_box((0.0, 0.0, 0.0), w, l, d)
    col_brep = builder.create_box((col_x0, col_y0, d), col_w, col_d, stub_h)

    blinding_metrics = builder.assert_valid(blinding_brep)
    pad_metrics = builder.assert_valid(pad_brep)
    col_metrics = builder.assert_valid(col_brep)

    prim_breps: dict[str, Any] = {
        "/World/Footing/Blinding": blinding_brep,
        "/World/Footing/PadConcrete": pad_brep,
        "/World/Footing/ColumnStub": col_brep,
    }
    render_parts: list[dict[str, Any]] = [
        {"brep": blinding_brep, "color": "#475569", "opacity": 0.45, "show_edges": True},
        {"brep": pad_brep, "color": "#94a3b8", "opacity": 0.25, "show_edges": True},
        {"brep": col_brep, "color": "#cbd5e1", "opacity": 0.28, "show_edges": True},
    ]

    # Bottom X-direction bars
    z_3d_x = cover + bot_dia / 2.0
    for idx, py in enumerate(dist_x["positions_mm"]):
        bar = builder.create_bar_3d((cover, py, z_3d_x), (w - cover, py, z_3d_x), bot_dia / 2.0)
        if idx == 0:
            builder.assert_valid(bar)
        prim_breps[f"/World/Footing/RebarCage/BottomX_{idx:02d}"] = bar
        render_parts.append({"brep": bar, "color": "#ef4444", "opacity": 1.0, "metallic": 0.6})

    # Bottom Y-direction bars
    z_3d_y = z_3d_x + bot_dia
    for idx, px in enumerate(dist_y["positions_mm"]):
        bar = builder.create_bar_3d((px, cover, z_3d_y), (px, l - cover, z_3d_y), bot_dia / 2.0)
        if idx == 0:
            builder.assert_valid(bar)
        prim_breps[f"/World/Footing/RebarCage/BottomY_{idx:02d}"] = bar
        render_parts.append({"brep": bar, "color": "#f59e0b", "opacity": 1.0, "metallic": 0.6})

    # Hooked starter dowels (90-deg L-bars)
    z_3d_dowel_base = z_3d_y + bot_dia / 2.0
    z_3d_dowel_top = d + dowel_proj
    cx_mid, cy_mid = w / 2.0, l / 2.0
    for idx, (dx, dy) in enumerate(dowel_pts):
        # Point hook outward radially along X or Y
        vx = dx - cx_mid
        vy = dy - cy_mid
        if abs(vx) >= abs(vy):
            hx = dx + math.copysign(dowel_hook, vx if vx != 0 else 1.0)
            hy = dy
        else:
            hx = dx
            hy = dy + math.copysign(dowel_hook, vy if vy != 0 else 1.0)
        dowel_bar = builder.create_l_bar_3d(
            (hx, hy, z_3d_dowel_base),
            (dx, dy, z_3d_dowel_base),
            (dx, dy, z_3d_dowel_top),
            dowel_dia / 2.0,
        )
        if idx == 0:
            builder.assert_valid(dowel_bar)
        prim_breps[f"/World/Footing/RebarCage/Dowel_{idx:02d}"] = dowel_bar
        render_parts.append({"brep": dowel_bar, "color": "#38bdf8", "opacity": 1.0, "metallic": 0.65})

    usd_path = builder.export_assembly_usd(prim_breps, out / "pad_footing.usd")

    # 5. Render Multi-Angle Translucent Concrete + Opaque Rebar Views
    renderer = Renderer3D()
    render_paths = renderer.render_assembly_views(
        render_parts,
        out / "renders",
        prefix="pad_footing",
        chord_height_tolerance=0.2,
    )

    # Concrete volumes in m^3 (1 m^3 = 1e9 mm^3)
    blinding_m3 = round(blinding_metrics["volume"] / 1e9, 4)
    pad_m3 = round(pad_metrics["volume"] / 1e9, 4)
    col_m3 = round(col_metrics["volume"] / 1e9, 4)

    summary = {
        "sketch_status": solved["status"],
        "sketch_dof": solved["dof"],
        "concrete_volumes_m3": {
            "blinding": blinding_m3,
            "pad_concrete": pad_m3,
            "column_stub": col_m3,
            "total_structural": round(pad_m3 + col_m3, 4),
        },
        "bar_bending_schedule": bbs_rows,
        "total_steel_mass_kg": total_steel_kg,
        "rebar_prim_count": len(prim_breps) - 3,
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
        f"Concrete={vols['total_structural']:.3f} m3 (Pad={vols['pad_concrete']:.3f}, Col={vols['column_stub']:.3f}) | "
        f"Total Steel={summary['total_steel_mass_kg']:.2f} kg | "
        f"3D Rebar Prims={summary['rebar_prim_count']}"
    )


if __name__ == "__main__":
    main()
