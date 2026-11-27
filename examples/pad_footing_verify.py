"""Phase 2 Step 1 verification: RC Pad Footing (v1 T16@150 4 dowels -> v2 T20@150 8 dowels)."""

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


def main() -> None:
    recipe_dir = REPO_ROOT / "recipes" / "rc_pad_footing"
    v1_params = json.loads((recipe_dir / "params.json").read_text(encoding="utf-8"))
    build_script = (recipe_dir / "build.py").read_text(encoding="utf-8")
    # Ensure copied build.py resolves REPO_ROOT even inside workspaces/pad_footing_demo/
    build_script = build_script.replace(
        "REPO_ROOT = Path(__file__).resolve().parents[2]",
        f'REPO_ROOT = Path(r"{REPO_ROOT}")',
    )

    ws_dir = REPO_ROOT / "workspaces" / "pad_footing_demo"
    wm = WorkspaceManager(ws_dir)
    wm.init_workspace(v1_params, build_script)

    print("=== Building v1 (2400x2400x600 mm, T16@150, 4 dowels) ===")
    v1_res = wm.run_build(python_exe=sys.executable)
    print(v1_res["stdout"].strip())
    v1_summary = json.loads((ws_dir / "summary.json").read_text(encoding="utf-8"))
    print("v1 BBS Total Steel Mass (kg):", v1_summary["total_steel_mass_kg"])
    print("v1 Concrete Volumes (m3):", v1_summary["concrete_volumes_m3"])

    print("\n=== Updating params -> v2 (2800x2800x650 mm, T20@150, 8 dowels) ===")
    wm.update_params(
        {
            "footing_width_mm": 2800.0,
            "footing_length_mm": 2800.0,
            "footing_depth_mm": 650.0,
            "bottom_bar_dia_mm": 20.0,
            "bottom_bar_spacing_mm": 150.0,
            "dowel_count": 8,
        }
    )
    v2_res = wm.run_build(python_exe=sys.executable)
    print(v2_res["stdout"].strip())
    v2_summary = json.loads((ws_dir / "summary.json").read_text(encoding="utf-8"))
    print("v2 BBS Total Steel Mass (kg):", v2_summary["total_steel_mass_kg"])
    print("v2 Concrete Volumes (m3):", v2_summary["concrete_volumes_m3"])

    ckpt_v1 = Path(v1_res["checkpoint_dir"])
    ckpt_v2 = Path(v2_res["checkpoint_dir"])

    print("\n=== Computing Visual Diff (v1 vs v2) ===")
    diff_dir = ws_dir / "diffs"
    for view in ("top", "iso"):
        diff = Renderer3D.compute_visual_diff(
            ckpt_v1 / "renders" / f"pad_footing_{view}.png",
            ckpt_v2 / "renders" / f"pad_footing_{view}.png",
            diff_dir / f"diff_v1_v2_{view}.png",
        )
        print(f"[{view}] SSIM={diff['ssim']}, changed_pixels={diff['changed_pixels_pct']}% -> {diff['diff_path']}")

    print("\n=== Verifying Checkpoint Rollback (restore_checkpoint(1)) ===")
    restore_v1 = wm.restore_checkpoint(1)
    restored_params = json.loads((ws_dir / "params.json").read_text(encoding="utf-8"))
    assert restored_params["footing_width_mm"] == 2400.0
    assert restored_params["dowel_count"] == 4
    print(f"Restored v1 OK: {restore_v1['files']}")


if __name__ == "__main__":
    main()
