"""Tests for Sketch-to-IR and Bounded Self-Repair & Provenance Loop."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import engine  # noqa: F401
from engine.repair_loop import run_bounded_repair
from engine.sketch_ir import compile_ir_to_params, parse_sketch_brief
import server

RECIPES_DIR = REPO_ROOT / "recipes"


def test_sketch_to_ir_extraction_and_confirmation_gate() -> None:
    brief = "Pad footing 2.4m x 2.4m x 600mm, f'c 25 MPa, T16@150"
    ir = parse_sketch_brief(brief)
    assert ir["target_template"] == "rc_pad_footing"
    assert ir["explicit_dimensions_mm"]["pad_width_mm"] == pytest.approx(2400.0)
    assert ir["explicit_dimensions_mm"]["pad_length_mm"] == pytest.approx(2400.0)
    assert ir["explicit_dimensions_mm"]["pad_depth_mm"] == pytest.approx(600.0)
    assert ir["explicit_dimensions_mm"]["mat_bar_dia_mm"] == pytest.approx(16.0)
    assert ir["explicit_dimensions_mm"]["mat_spacing_mm"] == pytest.approx(150.0)
    assert "col_width_mm" in ir["missing_params"]
    assert ir["needs_confirmation"] is True
    assert len(ir["confirmation_questions"]) >= 1

    compiled = compile_ir_to_params(
        ir,
        confirmed_updates={"col_width_mm": 400.0, "col_length_mm": 400.0},
        fill_defaults=True,
    )
    assert compiled["pad_width_mm"] == 2400.0
    assert compiled["col_width_mm"] == 400.0
    assert compiled["mat_bar_dia_mm"] == 16


def test_sketch_to_ir_flags_non_si_units() -> None:
    ir = parse_sketch_brief("Beam 12 ft span, 12 in x 24 in")
    assert ir["target_template"] == "rc_beam"
    assert ir["needs_confirmation"] is True
    assert len(ir["ambiguities"]) >= 1


def test_bounded_repair_fixes_rc_column_v1(tmp_path: Path) -> None:
    v1_params = json.loads((RECIPES_DIR / "rc_column" / "v1_params.json").read_text(encoding="utf-8"))
    prov = run_bounded_repair(
        recipe_name="rc_column",
        initial_params=v1_params,
        workspace_root=tmp_path / "col_repair",
        max_retries=3,
    )
    assert prov["final_status"] == "PASS"
    assert 1 <= prov["attempts_used"] <= 3
    assert Path(prov["provenance_path"]).is_file()
    final_attempt = prov["history"][-1]
    assert final_attempt["status"] == "PASS"
    assert final_attempt["params"]["vert_bar_count"] == 8
    assert final_attempt["params"]["has_crossties"] is True


def test_bounded_repair_enforces_retry_cap_and_restores_best(tmp_path: Path) -> None:
    # Impossible bearing limit (q_allow=10 kPa) cannot be satisfied in 2 +100mm steps
    v1_params = json.loads((RECIPES_DIR / "rc_pad_footing" / "v1_params.json").read_text(encoding="utf-8"))
    v1_params["q_allow_kpa"] = 10.0
    prov = run_bounded_repair(
        recipe_name="rc_pad_footing",
        initial_params=v1_params,
        workspace_root=tmp_path / "pf_cap",
        max_retries=2,
    )
    assert prov["max_retries"] == 2
    assert prov["attempts_used"] == 2
    assert prov["final_status"] == "FAIL"
    assert prov["restored_checkpoint"] == prov["best_checkpoint"]
    assert Path(prov["provenance_path"]).is_file()


def test_mcp_server_registers_ir_and_repair_tools() -> None:
    assert hasattr(server, "parse_sketch_to_ir")
    assert hasattr(server, "build_with_repair")
    assert hasattr(server, "inspect_provenance")
