"""Phase 1 end-to-end verification: parametric steel baseplate (v1 M16 -> v2 M20)."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import engine  # noqa: F401 — loads usd_brep before pxr
from engine.renderer import Renderer3D
from engine.workspace import WorkspaceManager

BUILD_SCRIPT = '''"""Parametric baseplate build script executed inside a Midusa workspace."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(r"__REPO_ROOT__")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import engine  # noqa: F401 — loads usd_brep before pxr
from engine.drafting_2d import Drafting2D
from engine.renderer import Renderer3D
from engine.sketch_bridge import SketchBridge
from engine.solid_3d import Solid3DBuilder


def main() -> None:
    ws = Path(__file__).resolve().parent
    params = json.loads((ws / "params.json").read_text(encoding="utf-8"))

    width = float(params["plate_width"])
    depth = float(params["plate_depth"])
    thickness = float(params["plate_thickness"])
    offset = float(params["edge_offset"])
    hole_dia = float(params["hole_diameter"])
    fillet_r = float(params["fillet_radius"])
    bolt_label = str(params["bolt_label"])

    # 1. Solve 2D parametric sketch with PlaneGCS (require DOF == 0)
    sketch = SketchBridge()
    sketch.add_rectangle("plate", 0.0, 0.0, width, depth, fix_origin=True)

    hole_targets = [
        ("h_bl", offset, offset),
        ("h_br", width - offset, offset),
        ("h_tr", width - offset, depth - offset),
        ("h_tl", offset, depth - offset),
    ]
    for name, hx, hy in hole_targets:
        c_pt = sketch.add_point(f"{name}_c", hx, hy, fixed=True)
        sketch.add_circle(name, c_pt, hole_dia / 2.0)
        sketch.constrain_circle_diameter(name, hole_dia)

    solved = sketch.solve(require_zero_dof=True)
    print(f"[SketchBridge] Solved {bolt_label}: status={solved['status']}, dof={solved['dof']}")

    # 2. Generate 2D DXF & PNG technical drawing with ezdxf
    draft = Drafting2D()
    draft.add_rectangle(0.0, 0.0, width, depth)
    for name, _, _ in hole_targets:
        (cx, cy), rad = sketch.get_circle(name)
        draft.add_circle(cx, cy, rad, with_centerlines=True)

    draft.add_linear_dim(base=(0.0, -15.0), p1=(0.0, 0.0), p2=(width, 0.0), angle=0.0)
    draft.add_linear_dim(base=(-15.0, 0.0), p1=(0.0, 0.0), p2=(0.0, depth), angle=90.0)
    (tr_cx, tr_cy), tr_rad = sketch.get_circle("h_tr")
    draft.add_diameter_dim(center=(tr_cx, tr_cy), radius=tr_rad, angle=45.0)
    draft.add_title_block(
        title=f"STEEL BASEPLATE ({bolt_label})",
        subtitle=f"{width:.0f} x {depth:.0f} x {thickness:.0f} mm | 4x Ø{hole_dia:.1f} mm",
        origin=(0.0, -40.0),
    )

    dxf_path = draft.save_dxf(ws / "baseplate.dxf")
    png2d_path = draft.export_png(ws / "baseplate_2d.png")
    print(f"[Drafting2D] Saved {dxf_path.name} and {png2d_path.name}")

    # 3. Build 3D B-Rep solid with usd-brep
    builder = Solid3DBuilder()
    plate = builder.create_box((0.0, 0.0, 0.0), width, depth, thickness)
    if fillet_r > 0.0:
        plate = builder.circular_fillet(plate, fillet_r)

    for name, _, _ in hole_targets:
        (cx, cy), rad = sketch.get_circle(name)
        hole_tool = builder.create_cylinder((cx, cy, -1.0), rad, thickness + 2.0)
        plate = builder.boolean_difference(plate, hole_tool)

    metrics = builder.assert_valid(plate)
    usd_path = builder.export_usd(plate, ws / "baseplate.usd")
    print(
        f"[Solid3DBuilder] Valid manifold solid: volume={metrics['volume']:.2f} mm^3, "
        f"usd={usd_path.name}"
    )

    # 4. Render multi-angle 3D PNGs with PyVista
    renderer = Renderer3D()
    views = renderer.render_views(plate, ws / "renders", prefix="baseplate")
    print(f"[Renderer3D] Rendered views: {sorted(views.keys())}")


if __name__ == "__main__":
    main()
'''.replace("__REPO_ROOT__", str(REPO_ROOT))


def main() -> None:
    ws_dir = REPO_ROOT / "workspaces" / "baseplate_demo"
    wm = WorkspaceManager(ws_dir)

    v1_params = {
        "bolt_label": "M16",
        "plate_width": 250.0,
        "plate_depth": 200.0,
        "plate_thickness": 20.0,
        "edge_offset": 35.0,
        "hole_diameter": 18.0,
        "fillet_radius": 3.0,
    }
    wm.init_workspace(v1_params, BUILD_SCRIPT)

    print("=== Building v1 (M16 holes) ===")
    v1_res = wm.run_build(python_exe=sys.executable)
    print(v1_res["stdout"].strip())

    print("\n=== Updating params -> v2 (M20 holes) ===")
    wm.update_params({"bolt_label": "M20", "hole_diameter": 22.0})
    v2_res = wm.run_build(python_exe=sys.executable)
    print(v2_res["stdout"].strip())

    ckpt_v1 = Path(v1_res["checkpoint_dir"])
    ckpt_v2 = Path(v2_res["checkpoint_dir"])

    print("\n=== Computing Visual Diff (v1 vs v2) ===")
    diff_dir = ws_dir / "diffs"
    for view in ("top", "iso"):
        diff = Renderer3D.compute_visual_diff(
            ckpt_v1 / "renders" / f"baseplate_{view}.png",
            ckpt_v2 / "renders" / f"baseplate_{view}.png",
            diff_dir / f"diff_v1_v2_{view}.png",
        )
        print(f"[{view}] SSIM={diff['ssim']}, changed_pixels={diff['changed_pixels_pct']}% -> {diff['diff_path']}")

    print("\n=== Verifying Checkpoint Rollback (restore v1 -> re-restore v2) ===")
    restore_v1 = wm.restore_checkpoint(1)
    assert json.loads((ws_dir / "params.json").read_text(encoding="utf-8"))["bolt_label"] == "M16"
    print(f"Restored v1 OK: {restore_v1['files']}")
    restore_v2 = wm.restore_checkpoint(2)
    assert json.loads((ws_dir / "params.json").read_text(encoding="utf-8"))["bolt_label"] == "M20"
    print(f"Restored v2 OK: {restore_v2['files']}")


if __name__ == "__main__":
    main()
