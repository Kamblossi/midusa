"""Deterministic SI metric acceptance test suite enforcing Section 4 gates."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import ezdxf
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import engine  # noqa: F401 — loads usd_brep before pxr
from engine.member_profiles import (
    solve_flanged_profile,
    solve_pad_footing_profile,
    solve_rect_profile,
    solve_retaining_wall_profile,
    solve_slab_profile,
)
from engine.rebar_detailing import distribute_multi_zone
from recipes.layout_roof_spec.build import build as build_layout_roof
from recipes.rc_beam.build import build as build_beam
from recipes.rc_column.build import build as build_column
from recipes.rc_pad_footing.build import build as build_pad_footing
from recipes.rc_slab.build import build as build_slab
from recipes.retaining_wall.build import build as build_retaining_wall
from rules.validator import load_rules

RECIPES_DIR = REPO_ROOT / "recipes"


def _load_params(template: str, version: str) -> dict:
    return json.loads((RECIPES_DIR / template / f"{version}_params.json").read_text(encoding="utf-8"))


def _bbs_map(summary: dict) -> dict[str, dict]:
    return {row["bar_mark"]: row for row in summary["bar_bending_schedule"]}


def _assert_dxf_valid(dxf_path: str | Path) -> None:
    doc = ezdxf.readfile(str(dxf_path))
    assert doc.header["$INSUNITS"] == 4
    auditor = doc.audit()
    assert len(auditor.errors) == 0


# ---------------------------------------------------------------------------
# Gate 1: Kernel, Rule Catalog, and Format Invariants
# ---------------------------------------------------------------------------


def test_gate_1_rule_catalog_and_profiles() -> None:
    rules = load_rules()
    assert len(rules) == 31

    p_rect = solve_rect_profile(250, 500, 5400, clear_span_mm=4800)
    assert p_rect["dof"] == 0 and p_rect["volume_m3"] == pytest.approx(0.675, abs=1e-4)

    p_t = solve_flanged_profile("T_BEAM", 250, 500, 800, 120, 5000)
    assert p_t["dof"] == 0 and len(p_t["vertices"]) == 8

    p_l = solve_flanged_profile("L_BEAM", 250, 500, 600, 120, 5000)
    assert p_l["dof"] == 0 and len(p_l["vertices"]) == 6

    p_slab = solve_slab_profile(4500, 3600, 150)
    assert p_slab["dof"] == 0 and p_slab["volume_m3"] == pytest.approx(2.430, abs=1e-4)

    p_pad = solve_pad_footing_profile(2400, 2400, 600, step_w_mm=400, step_l_mm=400, step_h_mm=600)
    assert p_pad["dof"] == 0 and p_pad["volume_m3"] == pytest.approx(3.552, abs=1e-4)

    p_rw = solve_retaining_wall_profile(2400, 250, 250, 400, 950, 350)
    assert p_rw["dof"] == 0 and p_rw["volume_m3"] == pytest.approx(5.800, abs=1e-4)


# ---------------------------------------------------------------------------
# Gate 2: Template 1 (rc_pad_footing)
# ---------------------------------------------------------------------------


def test_gate_2_rc_pad_footing_v1_and_v2(tmp_path: Path) -> None:
    s1 = build_pad_footing(_load_params("rc_pad_footing", "v1"), tmp_path / "pf_v1", render_3d=False)
    _assert_dxf_valid(s1["outputs"]["dxf"])
    assert s1["sketch_dof"] == 0
    assert s1["takeoff"]["structural_concrete_m3"] == pytest.approx(3.552, abs=0.001)
    assert s1["takeoff"]["blinding_concrete_m3"] == pytest.approx(0.3125, abs=0.001)
    bbs1 = _bbs_map(s1)
    assert bbs1["B1"]["total_qty"] == 16 and bbs1["B2"]["total_qty"] == 16
    assert bbs1["B1"]["cut_length_mm"] == 2690
    assert bbs1["D1"]["cut_length_mm"] == 2085
    assert bbs1["L1"]["total_qty"] == 5
    assert s1["total_steel_mass_kg"] == pytest.approx(160.82, abs=0.05)
    assert s1["metrics"]["q_gross_kpa"] == pytest.approx(188.41, abs=0.2)
    assert s1["metrics"]["v_u_punch_mpa"] == pytest.approx(0.620, abs=0.005)
    assert s1["metrics"]["rebar_to_rebar_overlap_vol"] == 0.0
    assert s1["metrics"]["min_cover_brep"] >= 40.0 - 0.5
    assert s1["compliance"]["status"] == "PASS"

    s2 = build_pad_footing(_load_params("rc_pad_footing", "v2"), tmp_path / "pf_v2", render_3d=False)
    _assert_dxf_valid(s2["outputs"]["dxf"])
    assert s2["takeoff"]["structural_concrete_m3"] == pytest.approx(5.2175, abs=0.001)
    assert s2["takeoff"]["blinding_concrete_m3"] == pytest.approx(0.4205, abs=0.001)
    bbs2 = _bbs_map(s2)
    assert bbs2["B1"]["total_qty"] == 19 and bbs2["B2"]["total_qty"] == 19
    assert bbs2["B1"]["cut_length_mm"] == 3190
    assert bbs2["D1"]["cut_length_mm"] == 2125
    assert s2["total_steel_mass_kg"] == pytest.approx(345.87, abs=0.05)
    assert s2["compliance"]["status"] == "PASS"
    assert len(s2["compliance"]["errors"]) == 0


# ---------------------------------------------------------------------------
# Gate 3: Template 2 (rc_beam)
# ---------------------------------------------------------------------------


def test_gate_3_rc_beam_v1_and_v2(tmp_path: Path) -> None:
    s1 = build_beam(_load_params("rc_beam", "v1"), tmp_path / "bm_v1", render_3d=False)
    _assert_dxf_valid(s1["outputs"]["dxf"])
    assert s1["takeoff"]["structural_concrete_m3"] == pytest.approx(0.675, abs=0.001)
    bbs1 = _bbs_map(s1)
    assert bbs1["B1"]["cut_length_mm"] == 5760
    assert bbs1["T1"]["cut_length_mm"] == 5650
    assert bbs1["L1"]["total_qty"] == 28
    assert s1["total_steel_mass_kg"] == pytest.approx(60.18, abs=0.05)
    warn_ids1 = {w["rule_id"] for w in s1["compliance"]["warnings"]}
    assert "R-DEV-02" in warn_ids1
    assert s1["metrics"]["l_dh_avail_mm"] == pytest.approx(260.0, abs=0.5)
    assert s1["metrics"]["l_dh_req_mm"] == pytest.approx(353.3, abs=0.5)

    # Verify zero duplicate bars at zone boundaries x=1100 and x=4300
    mz = distribute_multi_zone(5400.0, 1100.0, 125.0, 200.0, 10.0, c_end_mm=50.0)
    assert len(set(mz["end_positions_mm"]) & set(mz["mid_positions_mm"])) == 0
    assert 1100.0 not in mz["mid_positions_mm"] and 4300.0 not in mz["mid_positions_mm"]

    s2 = build_beam(_load_params("rc_beam", "v2"), tmp_path / "bm_v2", render_3d=False)
    _assert_dxf_valid(s2["outputs"]["dxf"])
    assert s2["takeoff"]["structural_concrete_m3"] == pytest.approx(0.825, abs=0.001)
    bbs2 = _bbs_map(s2)
    assert bbs2["B1"]["cut_length_mm"] == 6460
    assert bbs2["L1"]["total_qty"] == 20
    assert bbs2["L2"]["total_qty"] == 15
    assert s2["total_steel_mass_kg"] == pytest.approx(98.62, abs=0.05)
    assert s2["metrics"]["s_1_act_mm"] == pytest.approx(116.11, abs=0.05)
    assert s2["metrics"]["s_1_act_mm"] <= 122.5


# ---------------------------------------------------------------------------
# Gate 4: Template 3 (rc_column)
# ---------------------------------------------------------------------------


def test_gate_4_rc_column_v1_and_v2(tmp_path: Path) -> None:
    s1 = build_column(_load_params("rc_column", "v1"), tmp_path / "col_v1", render_3d=False)
    _assert_dxf_valid(s1["outputs"]["dxf"])
    assert s1["takeoff"]["structural_concrete_m3"] == pytest.approx(0.288, abs=0.001)
    assert s1["total_steel_mass_kg"] == pytest.approx(34.99, abs=0.05)
    err_ids1 = {e["rule_id"] for e in s1["compliance"]["errors"]}
    assert "R-STR-04" in err_ids1
    assert "R-SPC-04" in err_ids1
    assert s1["metrics"]["rho_g"] == pytest.approx(0.0089, abs=0.0005)
    assert s1["metrics"]["s_clr_face_mm"] == pytest.approx(168.0, abs=0.5)

    s2 = build_column(_load_params("rc_column", "v2"), tmp_path / "col_v2", render_3d=False)
    _assert_dxf_valid(s2["outputs"]["dxf"])
    assert s2["takeoff"]["structural_concrete_m3"] == pytest.approx(0.576, abs=0.001)
    bbs2 = _bbs_map(s2)
    assert bbs2["L1"]["total_qty"] == 23
    assert bbs2["L2"]["total_qty"] == 46
    assert s2["total_steel_mass_kg"] == pytest.approx(122.04, abs=0.05)
    assert s2["metrics"]["rho_g"] == pytest.approx(0.0157, abs=0.0005)
    assert s2["metrics"]["s_clr_face_mm"] == pytest.approx(120.0, abs=0.5)
    assert s2["compliance"]["status"] == "PASS"


# ---------------------------------------------------------------------------
# Gate 5: Template 4 (rc_slab)
# ---------------------------------------------------------------------------


def test_gate_5_rc_slab_v1_and_v2(tmp_path: Path) -> None:
    s1 = build_slab(_load_params("rc_slab", "v1"), tmp_path / "sl_v1", render_3d=False)
    _assert_dxf_valid(s1["outputs"]["dxf"])
    assert s1["takeoff"]["structural_concrete_m3"] == pytest.approx(2.430, abs=0.001)
    bbs1 = _bbs_map(s1)
    assert bbs1["B1"]["total_qty"] == 27 and bbs1["B1"]["cut_length_mm"] == 3550
    assert bbs1["B2"]["total_qty"] == 19 and bbs1["B2"]["cut_length_mm"] == 4450
    assert s1["total_steel_mass_kg"] == pytest.approx(137.22, abs=0.05)

    s2 = build_slab(_load_params("rc_slab", "v2"), tmp_path / "sl_v2", render_3d=False)
    _assert_dxf_valid(s2["outputs"]["dxf"])
    assert s2["takeoff"]["structural_concrete_m3"] == pytest.approx(3.500, abs=0.001)
    bbs2 = _bbs_map(s2)
    assert bbs2["B1"]["total_qty"] == 34
    assert bbs2["B2"]["total_qty"] == 24
    assert bbs2["T1a"]["total_qty"] == 52
    assert bbs2["T1b"]["total_qty"] == 42
    assert s2["metrics"]["n_t1"] == 94
    assert s2["total_steel_mass_kg"] == pytest.approx(287.00, abs=0.05)


# ---------------------------------------------------------------------------
# Gate 6: Template 5A (retaining_wall) & Template 5B (layout_roof_spec)
# ---------------------------------------------------------------------------


def test_gate_6_retaining_wall_and_layout_roof(tmp_path: Path) -> None:
    rw1 = build_retaining_wall(_load_params("retaining_wall", "v1"), tmp_path / "rw_v1", render_3d=False)
    _assert_dxf_valid(rw1["outputs"]["dxf"])
    assert rw1["takeoff"]["structural_concrete_m3"] == pytest.approx(5.800, abs=0.001)
    assert rw1["total_steel_mass_kg"] == pytest.approx(571.25, abs=0.05)
    assert rw1["metrics"]["FoS_OT"] == pytest.approx(2.38, abs=0.02)
    assert rw1["metrics"]["FoS_SL"] == pytest.approx(1.13, abs=0.02)
    assert "R-GEO-02" in {e["rule_id"] for e in rw1["compliance"]["errors"]}

    rw2 = build_retaining_wall(_load_params("retaining_wall", "v2"), tmp_path / "rw_v2", render_3d=False)
    _assert_dxf_valid(rw2["outputs"]["dxf"])
    assert rw2["takeoff"]["structural_concrete_m3"] == pytest.approx(8.950, abs=0.001)
    assert rw2["total_steel_mass_kg"] == pytest.approx(977.41, abs=0.05)
    assert rw2["metrics"]["FoS_OT"] == pytest.approx(2.56, abs=0.02)
    assert rw2["metrics"]["q_max_kpa"] == pytest.approx(102.34, abs=0.1)
    assert rw2["metrics"]["FoS_SL"] == pytest.approx(1.75, abs=0.02)
    assert rw2["compliance"]["status"] == "PASS"

    lr1 = build_layout_roof(_load_params("layout_roof_spec", "v1"), tmp_path / "lr_v1", render_3d=False)
    _assert_dxf_valid(lr1["outputs"]["dxf"])
    assert lr1["concrete_volumes_m3"]["total_frame_structural"] == pytest.approx(20.213, abs=0.005)
    assert lr1["roof"]["H_ridge_mm"] == pytest.approx(1242.6, abs=0.5)
    assert lr1["roof"]["L_rafter_mm"] == pytest.approx(3896.6, abs=0.5)
    assert lr1["roof"]["n_truss_assemblies"] == 11
    assert lr1["roof"]["n_purlin_lines"] == 10
    assert lr1["roof"]["total_purlin_run_m"] == pytest.approx(84.00, abs=0.05)

    lr2 = build_layout_roof(_load_params("layout_roof_spec", "v2"), tmp_path / "lr_v2", render_3d=False)
    _assert_dxf_valid(lr2["outputs"]["dxf"])
    # Exact geometric sum: 14.580 + 2.592 + 2.2275 + 1.8225 + 0.3645 (9*0.3*0.3*0.45) + 5.346 = 26.933 m3
    assert lr2["concrete_volumes_m3"]["total_frame_structural"] == pytest.approx(26.933, abs=0.005)
