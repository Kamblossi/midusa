"""Bounded self-repair loop with WorkspaceManager checkpoints and provenance logging."""

from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
from typing import Any

from engine.workspace import WorkspaceManager

REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPES_DIR = REPO_ROOT / "recipes"

BAR_DIAS = [10, 12, 16, 20, 25, 32]


def _next_bar_dia(current: float) -> int:
    c = int(round(float(current)))
    for d in BAR_DIAS:
        if d > c:
            return d
    return c


def _propose_repairs(
    recipe_name: str,
    params: dict[str, Any],
    compliance: dict[str, Any],
    metrics: dict[str, Any],
    strict_warnings: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Compute deterministic parameter edits from failing rule IDs and repair hints."""
    findings = list(compliance.get("errors", []))
    if strict_warnings:
        findings.extend(compliance.get("warnings", []))

    updates: dict[str, Any] = {}
    applied: list[str] = []

    for f in findings:
        rid = f["rule_id"]
        if rid == "R-COV-01":
            key = "pad_cover_mm" if recipe_name == "rc_pad_footing" else "cover_earth_mm"
            if float(params.get(key, 0.0)) < 75.0:
                updates[key] = 75.0
                applied.append(f"{rid}: {key}=75.0")
        elif rid == "R-COV-02":
            key = "cover_exposed_mm" if recipe_name == "retaining_wall" else "cover_mm"
            if float(params.get(key, 0.0)) < 40.0:
                updates[key] = 40.0
                applied.append(f"{rid}: {key}=40.0")
        elif rid == "R-COV-03":
            updates["cover_top_mm"] = max(25.0, float(params.get("cover_top_mm", 25.0)))
            updates["cover_bot_mm"] = max(25.0, float(params.get("cover_bot_mm", 25.0)))
            applied.append(f"{rid}: cover_top/bot >= 25.0")
        elif rid == "R-STR-04" and recipe_name == "rc_column":
            cur_dia = int(params.get("vert_bar_dia_mm", 16))
            nxt = _next_bar_dia(cur_dia)
            if nxt > cur_dia:
                updates["vert_bar_dia_mm"] = nxt
                applied.append(f"{rid}: vert_bar_dia_mm {cur_dia}->{nxt}")
            else:
                updates["vert_bar_count"] = max(8, int(params.get("vert_bar_count", 4)))
                applied.append(f"{rid}: vert_bar_count={updates['vert_bar_count']}")
        elif rid == "R-SPC-04" and recipe_name == "rc_column":
            updates["vert_bar_count"] = max(8, int(params.get("vert_bar_count", 4)))
            updates["has_crossties"] = True
            applied.append(f"{rid}: vert_bar_count={updates['vert_bar_count']}, has_crossties=True")
        elif rid in {"R-SPC-07", "R-SPC-08"} and recipe_name == "rc_column":
            updates["tie_conf_spacing_mm"] = min(125.0, float(params.get("tie_conf_spacing_mm", 150.0)))
            updates["tie_mid_spacing_mm"] = min(200.0, float(params.get("tie_mid_spacing_mm", 200.0)))
            h_col = float(params.get("depth_mm", 400.0))
            h_clr = float(params.get("clear_height_mm", 3200.0))
            updates["confinement_len_mm"] = max(h_col, h_clr / 6.0, 450.0)
            applied.append(f"{rid}: tightened tie spacing and confinement_len_mm")
        elif rid == "R-DEV-03" and recipe_name == "rc_column":
            l_sc = float(metrics.get("l_sc_mm", 720.0))
            updates["lap_projection_mm"] = float(math.ceil(l_sc / 5.0) * 5.0)
            applied.append(f"{rid}: lap_projection_mm={updates['lap_projection_mm']}")
        elif rid == "R-GEO-02" and recipe_name == "retaining_wall":
            cur_dk = float(params.get("shear_key_depth_mm", 0.0))
            updates["shear_key_width_mm"] = max(300.0, float(params.get("shear_key_width_mm", 0.0)))
            updates["shear_key_depth_mm"] = max(300.0, cur_dk + 100.0)
            updates["heel_width_mm"] = float(params.get("heel_width_mm", 950.0)) + 200.0
            updates["mu_base_friction"] = max(float(params.get("mu_base_friction", 0.45)), math.tan(math.radians(float(params.get("phi_deg", 30.0)))))
            applied.append(f"{rid}: added/deepened shear key & widened heel")
        elif rid == "R-GEO-01" and recipe_name == "retaining_wall":
            updates["heel_width_mm"] = float(params.get("heel_width_mm", 950.0)) + 200.0
            applied.append(f"{rid}: heel_width_mm={updates['heel_width_mm']}")
        elif rid == "R-GEO-03" and recipe_name == "retaining_wall":
            updates["toe_width_mm"] = float(params.get("toe_width_mm", 400.0)) + 100.0
            updates["heel_width_mm"] = float(params.get("heel_width_mm", 950.0)) + 100.0
            applied.append(f"{rid}: widened toe and heel +100 mm")
        elif rid == "R-DEV-02" and recipe_name == "rc_beam":
            req = float(metrics.get("l_dh_req_mm", 360.0))
            cov = float(params.get("cover_mm", 40.0))
            new_sup = float(math.ceil((req + cov) / 50.0) * 50.0)
            updates["support_width_left_mm"] = max(new_sup, float(params.get("support_width_left_mm", 300.0)))
            updates["support_width_right_mm"] = max(new_sup, float(params.get("support_width_right_mm", 300.0)))
            applied.append(f"{rid}: support_width_mm={new_sup}")
        elif rid == "R-SPC-01":
            updates["width_mm"] = float(params.get("width_mm", 250.0)) + 50.0
            applied.append(f"{rid}: width_mm={updates['width_mm']}")
        elif rid == "R-BRG-01" and recipe_name == "rc_pad_footing":
            updates["pad_width_mm"] = float(params.get("pad_width_mm", 2400.0)) + 100.0
            updates["pad_length_mm"] = float(params.get("pad_length_mm", 2400.0)) + 100.0
            applied.append(f"{rid}: pad_width/length +100 mm")
        elif rid in {"R-STR-01", "R-STR-02"} and recipe_name == "rc_pad_footing":
            updates["pad_depth_mm"] = float(params.get("pad_depth_mm", 600.0)) + 50.0
            applied.append(f"{rid}: pad_depth_mm={updates['pad_depth_mm']}")

    return updates, applied


def _make_workspace_build_script(recipe_name: str) -> str:
    return f'''"""Auto-generated Midusa repair-loop build script for {recipe_name}."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(r"{REPO_ROOT}")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from recipes.{recipe_name}.build import build


def main() -> None:
    ws = Path(__file__).resolve().parent
    params = json.loads((ws / "params.json").read_text(encoding="utf-8"))
    build(params, ws, render_3d=False)


if __name__ == "__main__":
    main()
'''


def run_bounded_repair(
    recipe_name: str,
    initial_params: dict[str, Any],
    workspace_root: str | Path | None = None,
    max_retries: int = 3,
    strict_warnings: bool = False,
    sketch_ir: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run bounded self-repair loop over a recipe with WorkspaceManager checkpoints and provenance."""
    retries = max(1, min(5, int(max_retries)))
    if not (RECIPES_DIR / recipe_name / "build.py").is_file():
        raise ValueError(f"Unknown recipe: {recipe_name}")

    if workspace_root is None:
        ws_path = Path(tempfile.mkdtemp(prefix=f"midusa_repair_{recipe_name}_"))
    else:
        ws_path = Path(workspace_root)

    wm = WorkspaceManager(ws_path)
    current_params = dict(initial_params)
    wm.init_workspace(current_params, _make_workspace_build_script(recipe_name))

    history: list[dict[str, Any]] = []
    best_checkpoint = 1
    best_score: tuple[int, int] | None = None
    final_status = "FAIL"
    last_outputs: dict[str, Any] = {}

    for attempt_idx in range(retries + 1):
        res = wm.run_build()
        ver = int(res["version"])
        summary = json.loads((wm.root / "summary.json").read_text(encoding="utf-8"))
        compliance = summary.get("compliance", {"status": "PASS", "errors": [], "warnings": []})
        metrics = summary.get("metrics", {})
        last_outputs = summary.get("outputs", {})

        n_err = len(compliance.get("errors", []))
        n_warn = len(compliance.get("warnings", []))
        score = (n_err, n_warn if strict_warnings else 0)
        if best_score is None or score < best_score:
            best_score = score
            best_checkpoint = ver

        is_passing = (compliance.get("status") == "PASS") and (not strict_warnings or n_warn == 0)
        history.append(
            {
                "attempt": attempt_idx,
                "checkpoint": ver,
                "params": dict(current_params),
                "status": compliance.get("status", "PASS"),
                "errors": compliance.get("errors", []),
                "warnings": compliance.get("warnings", []),
                "applied_repairs": [],
            }
        )

        if is_passing:
            final_status = "PASS"
            break

        if attempt_idx >= retries:
            final_status = "FAIL"
            break

        updates, applied = _propose_repairs(recipe_name, current_params, compliance, metrics, strict_warnings)
        if not updates:
            final_status = "FAIL"
            break

        history[-1]["applied_repairs"] = applied
        current_params = wm.update_params(updates)

    restored_checkpoint = history[-1]["checkpoint"]
    if final_status != "PASS":
        wm.restore_checkpoint(best_checkpoint)
        restored_checkpoint = best_checkpoint

    provenance = {
        "recipe_name": recipe_name,
        "workspace_dir": str(wm.root),
        "max_retries": retries,
        "attempts_used": len(history) - 1,
        "final_status": final_status,
        "best_checkpoint": best_checkpoint,
        "restored_checkpoint": restored_checkpoint,
        "sketch_ir": sketch_ir,
        "history": history,
        "outputs": last_outputs,
    }
    prov_path = wm.root / "repair_provenance.json"
    prov_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    provenance["provenance_path"] = str(prov_path)
    return provenance
