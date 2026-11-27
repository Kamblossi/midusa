"""Deterministic 31-rule ACI/BS/EC2 metric compliance validator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RULES_PATH = Path(__file__).resolve().parent / "aci_metric_rules.json"


def load_rules() -> list[dict[str, Any]]:
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    return list(data["rules"])


def _check_single_rule(
    rule_id: str,
    template_name: str,
    params: dict[str, Any],
    m: dict[str, Any],
) -> tuple[bool, str]:
    """Evaluate a single rule_id against params and solved metrics; return (passed, detail)."""
    if rule_id == "R-COV-01":
        cov = float(m.get("cover_earth_mm", params.get("pad_cover_mm", params.get("cover_earth_mm", 75.0))))
        return cov >= 75.0, f"cover_earth_mm={cov} < 75.0"
    if rule_id == "R-COV-02":
        cov = float(m.get("cover_exposed_mm", params.get("cover_mm", params.get("cover_exposed_mm", 40.0))))
        return cov >= 40.0, f"cover_exposed_mm={cov} < 40.0"
    if rule_id == "R-COV-03":
        ct = float(params.get("cover_top_mm", 25.0))
        cb = float(params.get("cover_bot_mm", 25.0))
        return (ct >= 20.0 and cb >= 20.0), f"cover_top={ct}, cover_bot={cb} < 20.0"

    if rule_id == "R-SPC-01":
        s_clr = float(m.get("s_clear_mm", 999.0))
        s_req = float(m.get("s_clear_min_mm", 25.0))
        return s_clr >= s_req, f"s_clear={s_clr:.1f} < {s_req:.1f}"
    if rule_id == "R-SPC-02":
        s_act = float(m.get("s_actual_mm", 0.0))
        s_max = min(3.0 * float(params.get("pad_depth_mm", 600.0)), 450.0)
        return s_act <= s_max, f"s_actual={s_act:.1f} > {s_max:.1f}"
    if rule_id == "R-SPC-03":
        s_b1 = float(m.get("s_b1_act_mm", 0.0))
        s_b2 = float(m.get("s_b2_act_mm", 0.0))
        h = float(params.get("thickness_mm", 150.0))
        return (s_b1 <= min(2.0 * h, 300.0) and s_b2 <= min(3.0 * h, 450.0)), (
            f"s_b1={s_b1:.1f}, s_b2={s_b2:.1f}"
        )
    if rule_id == "R-SPC-04":
        s_face = float(m.get("s_clr_face_mm", 0.0))
        return s_face <= 150.0, f"s_clr_face={s_face:.1f} > 150.0"
    if rule_id == "R-SPC-05":
        s_end = float(m.get("s_1_act_mm", 0.0))
        s_lim = float(m.get("s_1_max_seis_mm", 999.0))
        return s_end <= s_lim, f"s_1_act={s_end:.2f} > {s_lim:.2f}"
    if rule_id == "R-SPC-06":
        s_mid = float(m.get("s_2_act_mm", 0.0))
        s_lim = float(m.get("s_2_max_mm", 300.0))
        return s_mid <= s_lim, f"s_2_act={s_mid:.2f} > {s_lim:.2f}"
    if rule_id == "R-SPC-07":
        s_conf = float(m.get("s_conf_act_mm", 0.0))
        s_lim = float(m.get("s_conf_max_mm", 300.0))
        return s_conf <= s_lim, f"s_conf_act={s_conf:.2f} > {s_lim:.2f}"
    if rule_id == "R-SPC-08":
        s_mid = float(m.get("s_mid_act_mm", 0.0))
        s_lim = float(m.get("s_mid_max_mm", 300.0))
        return s_mid <= s_lim, f"s_mid_act={s_mid:.2f} > {s_lim:.2f}"

    if rule_id in {"R-BND-01", "R-BND-02", "R-BND-03"}:
        return bool(m.get(f"{rule_id}_ok", True)), f"{rule_id} check failed"
    if rule_id == "R-BND-04":
        off = float(params.get("crank_offset_mm", 0.0))
        if off <= 0.0 or params.get("splice_mode", "STRAIGHT_LAP") != "CRANK":
            return True, ""
        crank_h = float(m.get("crank_h_mm", 600.0))
        return (off / crank_h <= 1.0 / 6.0 and off < 75.0), f"crank_offset={off}"

    if rule_id == "R-DEV-01":
        avail = float(m.get("l_d_avail_mm", 9999.0))
        req = float(m.get("l_dh_req_mm", m.get("l_d_req_mm", 0.0)))
        return avail >= req, f"l_d_avail={avail:.1f} < {req:.1f}"
    if rule_id == "R-DEV-02":
        avail = float(m.get("l_dh_avail_mm", 9999.0))
        req = float(m.get("l_dh_req_mm", 0.0))
        h90 = float(m.get("H_90_mm", 0.0))
        h_avail = float(m.get("h_minus_2c_mm", 9999.0))
        return (avail >= req and h90 <= h_avail), f"l_dh_avail={avail:.1f} < l_dh_req={req:.1f}"
    if rule_id == "R-DEV-03":
        if template_name == "rc_column":
            lap = float(params.get("lap_projection_mm", 0.0))
            l_sc = float(m.get("l_sc_mm", 0.0))
            return lap >= l_sc, f"lap_projection={lap:.1f} < l_sc={l_sc:.1f}"
        emb = float(m.get("dowel_pad_emb_mm", 9999.0))
        l_dc = float(m.get("l_dc_pad_mm", 0.0))
        return emb >= l_dc, f"pad_emb={emb:.1f} < l_dc_pad={l_dc:.1f}"
    if rule_id == "R-DEV-04":
        max_dia = float(m.get("max_lap_dia_mm", 20.0))
        return max_dia <= 36.0, f"max_lap_dia={max_dia} > 36"

    if rule_id == "R-STR-01":
        return float(m.get("v_u_punch_mpa", 0.0)) <= float(m.get("phi_v_c_punch_mpa", 999.0)), (
            f"v_u={m.get('v_u_punch_mpa')} > phi*v_c={m.get('phi_v_c_punch_mpa')}"
        )
    if rule_id == "R-STR-02":
        return float(m.get("V_u_1w_kn", 0.0)) <= float(m.get("phi_V_c_1w_kn", 9999.0)), (
            f"V_u_1w={m.get('V_u_1w_kn')} > phi*V_c_1w={m.get('phi_V_c_1w_kn')}"
        )
    if rule_id == "R-STR-03":
        mu = float(m.get("M_u_knm", 0.0))
        pmn = float(m.get("phi_M_n_knm", 99999.0))
        as_prov = float(m.get("A_s_prov_mm2", 99999.0))
        as_min = float(m.get("A_s_min_mm2", 0.0))
        return (mu <= pmn and as_prov >= as_min), f"M_u={mu:.2f}/{pmn:.2f}, A_s={as_prov:.1f}/{as_min:.1f}"
    if rule_id == "R-STR-04":
        rho = float(m.get("rho_g", 0.02))
        n_bars = int(params.get("vert_bar_count", 4))
        min_bars = 4 if params.get("shape_type", "RECT") == "RECT" else 6
        return (0.01 <= rho <= 0.04 and n_bars >= min_bars), f"rho_g={rho:.4f} not in [0.01, 0.04]"
    if rule_id == "R-STR-05":
        as_pm = float(m.get("A_s_min_pm_prov_mm2", 9999.0))
        as_req = float(m.get("A_s_min_pm_req_mm2", 0.0))
        return as_pm >= as_req, f"A_s_pm={as_pm:.1f} < {as_req:.1f}"

    if rule_id == "R-BRG-01":
        qg = float(m.get("q_gross_kpa", 0.0))
        qa = float(params.get("q_allow_kpa", 200.0))
        return qg <= qa, f"q_gross={qg:.2f} > q_allow={qa:.2f}"
    if rule_id == "R-BRG-02":
        pu = float(m.get("P_u_kn", 0.0))
        b_min = min(float(m.get("phi_B_n_pad_kn", 99999.0)), float(m.get("phi_B_n_col_kn", 99999.0)))
        return pu <= b_min, f"P_u={pu:.1f} > phi*B_n={b_min:.1f}"

    if rule_id == "R-GEO-01":
        fos = float(m.get("FoS_OT", 99.0))
        e = float(m.get("eccentricity_mm", 0.0))
        b_6 = float(m.get("B_base_mm", 1800.0)) / 6.0
        return (fos >= 2.0 and e <= b_6), f"FoS_OT={fos:.2f}, e={e:.1f}/{b_6:.1f}"
    if rule_id == "R-GEO-02":
        fos_sl = float(m.get("FoS_SL", 99.0))
        return fos_sl >= 1.50, f"FoS_SL={fos_sl:.2f} < 1.50"
    if rule_id == "R-GEO-03":
        q_max = float(m.get("q_max_kpa", 0.0))
        q_min = float(m.get("q_min_kpa", 0.0))
        q_allow = float(params.get("q_allow_kpa", 150.0))
        return (q_max <= q_allow and q_min >= 0.0), f"q_max={q_max:.2f}, q_min={q_min:.2f}"

    if rule_id == "R-3D-01":
        ov = float(m.get("rebar_to_rebar_overlap_vol", 0.0))
        return ov == 0.0, f"rebar_overlap_vol={ov} != 0.0"
    if rule_id == "R-3D-02":
        cov_3d = float(m.get("min_cover_brep", 999.0))
        cov_req = float(m.get("cover_req_mm", 0.0))
        return cov_3d >= cov_req - 0.5, f"min_cover_brep={cov_3d} < {cov_req - 0.5}"

    return True, ""


def evaluate_rules(
    template_name: str,
    params: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate all applicable rules from aci_metric_rules.json and return PASS/FAIL report."""
    rules = load_rules()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    repair_hints: list[str] = []
    checked: list[str] = []

    for rule in rules:
        applies = rule["applies_to"]
        if "all" not in applies and template_name not in applies:
            continue
        rid = rule["rule_id"]
        checked.append(rid)
        passed, detail = _check_single_rule(rid, template_name, params, metrics)
        if not passed:
            entry = {
                "rule_id": rid,
                "category": rule["category"],
                "severity": rule["severity"],
                "detail": detail,
                "repair_hint": rule["repair_hint"],
            }
            if rule["severity"] == "ERROR":
                errors.append(entry)
            else:
                warnings.append(entry)
            repair_hints.append(f"{rid}: {rule['repair_hint']}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "repair_hints": repair_hints,
        "checked_rules": checked,
    }
