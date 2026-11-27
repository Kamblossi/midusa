"""Two-stage SI metric Rough Sketch-to-IR parser and compiler."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Callable

from pydantic import BaseModel, Field

RECIPES_DIR = Path(__file__).resolve().parent.parent / "recipes"

TEMPLATE_REQUIRED_PARAMS: dict[str, list[str]] = {
    "rc_pad_footing": [
        "pad_width_mm",
        "pad_length_mm",
        "pad_depth_mm",
        "col_width_mm",
        "col_length_mm",
        "pad_cover_mm",
        "mat_bar_dia_mm",
        "mat_spacing_mm",
    ],
    "rc_beam": [
        "clear_span_mm",
        "width_mm",
        "depth_mm",
        "cover_mm",
        "bot_bar_count",
        "bot_bar_dia_mm",
        "link_dia_mm",
        "link_mid_spacing_mm",
    ],
    "rc_column": [
        "width_mm",
        "depth_mm",
        "clear_height_mm",
        "cover_mm",
        "vert_bar_count",
        "vert_bar_dia_mm",
        "tie_dia_mm",
        "tie_mid_spacing_mm",
    ],
    "rc_slab": [
        "length_x_mm",
        "length_y_mm",
        "thickness_mm",
        "cover_bot_mm",
        "b1_dia_mm",
        "b1_spacing_mm",
        "b2_dia_mm",
        "b2_spacing_mm",
    ],
    "retaining_wall": [
        "stem_height_mm",
        "stem_base_thick_mm",
        "toe_width_mm",
        "heel_width_mm",
        "base_thick_mm",
        "s1_dia_mm",
        "s1_spacing_mm",
    ],
    "layout_roof_spec": [
        "x_bays_mm",
        "y_bays_mm",
        "story_height_mm",
        "pitch_deg",
        "clear_span_mm",
    ],
}


class SketchIR(BaseModel):
    """Structured SI metric Intermediate Representation extracted from rough sketch briefs."""

    target_template: str | None = None
    explicit_dimensions_mm: dict[str, float] = Field(default_factory=dict)
    inferred_constraints: list[dict[str, Any]] = Field(default_factory=list)
    missing_params: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    needs_confirmation: bool = False
    confirmation_questions: list[str] = Field(default_factory=list)


def _to_mm(value: float, unit: str) -> float:
    u = unit.lower().strip()
    if u == "m":
        return round(value * 1000.0, 3)
    return round(value, 3)


def _detect_template(text: str, template_hint: str | None) -> tuple[str | None, list[dict[str, Any]]]:
    inferred: list[dict[str, Any]] = []
    if template_hint and template_hint in TEMPLATE_REQUIRED_PARAMS:
        inferred.append({"constraint": f"template={template_hint}", "reason": "explicit template_hint", "confidence": 1.0})
        return template_hint, inferred

    low = text.lower()
    keyword_map = [
        ("retaining_wall", ["retaining wall", "cantilever wall", "heel", "toe", "shear key"]),
        ("rc_pad_footing", ["pad footing", "footing", "blinding", "starter dowel"]),
        ("layout_roof_spec", ["roof", "truss", "purlin", "gable", "building frame", "layout"]),
        ("rc_column", ["column", "pillar", "crosstie", "confinement"]),
        ("rc_beam", ["beam", "lintel", "spandrel", "stirrup", "clear span"]),
        ("rc_slab", ["slab", "panel", "shrinkage", "top strip"]),
    ]
    for tmpl, kws in keyword_map:
        for kw in kws:
            if kw in low:
                inferred.append({"constraint": f"template={tmpl}", "reason": f"matched keyword '{kw}'", "confidence": 0.9})
                return tmpl, inferred
    return None, inferred


def parse_sketch_brief(
    text_or_notes: str,
    template_hint: str | None = None,
    metadata: dict[str, Any] | None = None,
    llm_extractor: Callable[[str, str | None, dict[str, Any] | None], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse a rough engineering brief into a validated SI metric SketchIR payload."""
    text = str(text_or_notes or "")
    meta = dict(metadata or {})

    explicit_dims: dict[str, float] = {}
    inferred: list[dict[str, Any]] = []
    ambiguities: list[str] = []

    if llm_extractor is not None:
        llm_out = llm_extractor(text, template_hint, meta)
        if isinstance(llm_out, dict):
            template_hint = llm_out.get("target_template") or template_hint
            for k, v in (llm_out.get("explicit_dimensions_mm") or {}).items():
                explicit_dims[str(k)] = float(v)
            inferred.extend(llm_out.get("inferred_constraints") or [])
            ambiguities.extend(llm_out.get("ambiguities") or [])

    target_template, tmpl_inferred = _detect_template(text, template_hint)
    inferred.extend(tmpl_inferred)

    # Check for non-SI / ambiguous units
    non_si_matches = re.findall(r"\b\d+(?:\.\d+)?\s*(ft|feet|in|inch|inches|psi|ksi|psf|kip|kips)\b", text, flags=re.I)
    if non_si_matches:
        ambiguities.append(
            f"Non-SI unit(s) detected ({', '.join(sorted(set(m.lower() for m in non_si_matches)))}); "
            "Midusa requires strict SI metric (mm, m, MPa, kN, kPa)."
        )

    # Extract 3-axis dimensions like 2400x2400x600mm or 2.4m x 2.4m x 0.6m
    triple_re = re.search(
        r"(\d+(?:\.\d+)?)\s*(mm|m)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(mm|m)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(mm|m)\b",
        text,
        flags=re.I,
    )
    if triple_re:
        v1, u1, v2, u2, v3, u3 = triple_re.groups()
        u_def = u3 or "mm"
        d1 = _to_mm(float(v1), u1 or u_def)
        d2 = _to_mm(float(v2), u2 or u_def)
        d3 = _to_mm(float(v3), u3)
        if target_template == "rc_pad_footing":
            explicit_dims.setdefault("pad_width_mm", d1)
            explicit_dims.setdefault("pad_length_mm", d2)
            explicit_dims.setdefault("pad_depth_mm", d3)
        elif target_template == "rc_slab":
            explicit_dims.setdefault("length_x_mm", d1)
            explicit_dims.setdefault("length_y_mm", d2)
            explicit_dims.setdefault("thickness_mm", d3)
        else:
            explicit_dims.setdefault("width_mm", d1)
            explicit_dims.setdefault("depth_mm", d2)
            explicit_dims.setdefault("length_mm", d3)

    # Extract 2-axis dimensions like 300x300mm or 250 x 500 mm
    if not triple_re:
        pair_re = re.search(
            r"(\d+(?:\.\d+)?)\s*(mm|m)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(mm|m)\b",
            text,
            flags=re.I,
        )
        if pair_re:
            v1, u1, v2, u2 = pair_re.groups()
            d1 = _to_mm(float(v1), u1 or u2)
            d2 = _to_mm(float(v2), u2)
            if target_template == "rc_pad_footing":
                explicit_dims.setdefault("pad_width_mm", d1)
                explicit_dims.setdefault("pad_length_mm", d2)
            elif target_template == "rc_slab":
                explicit_dims.setdefault("length_x_mm", d1)
                explicit_dims.setdefault("length_y_mm", d2)
            else:
                explicit_dims.setdefault("width_mm", d1)
                explicit_dims.setdefault("depth_mm", d2)

    # Named scalar dimensions (span, height, depth, width, cover, thickness)
    named_patterns = [
        (r"(?:clear\s*span|span)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*(mm|m)\b", "clear_span_mm"),
        (r"(?:clear\s*height|height|stem\s*height)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*(mm|m)\b", "height_mm"),
        (r"(?:cover)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*(mm|m)\b", "cover_mm"),
        (r"(?:depth|thickness)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*(mm|m)\b", "depth_mm"),
    ]
    for pat, key in named_patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            val = _to_mm(float(m.group(1)), m.group(2))
            if key == "height_mm":
                if target_template == "rc_column":
                    explicit_dims.setdefault("clear_height_mm", val)
                elif target_template == "retaining_wall":
                    explicit_dims.setdefault("stem_height_mm", val)
                elif target_template == "layout_roof_spec":
                    explicit_dims.setdefault("story_height_mm", val)
            elif key == "cover_mm":
                if target_template == "rc_pad_footing":
                    explicit_dims.setdefault("pad_cover_mm", val)
                elif target_template == "rc_slab":
                    explicit_dims.setdefault("cover_bot_mm", val)
                else:
                    explicit_dims.setdefault("cover_mm", val)
            elif key == "depth_mm":
                if target_template == "rc_pad_footing":
                    explicit_dims.setdefault("pad_depth_mm", val)
                elif target_template == "rc_slab":
                    explicit_dims.setdefault("thickness_mm", val)
                else:
                    explicit_dims.setdefault("depth_mm", val)
            else:
                explicit_dims.setdefault(key, val)

    # Material strengths (MPa)
    fc_m = re.search(r"f'?c\s*(?:=|of)?\s*(\d+(?:\.\d+)?)\s*MPa", text, flags=re.I)
    if fc_m:
        fc_val = float(fc_m.group(1))
        if target_template == "rc_pad_footing":
            explicit_dims.setdefault("fc_pad_mpa", fc_val)
        else:
            explicit_dims.setdefault("fc_mpa", fc_val)
    fy_m = re.search(r"fy\s*(?:=|of)?\s*(\d+(?:\.\d+)?)\s*MPa", text, flags=re.I)
    if fy_m:
        explicit_dims.setdefault("fy_mpa", float(fy_m.group(1)))

    # Rebar callouts: T16@150 or R10@200
    at_m = re.search(r"\b([TR])(\d{1,2})\s*@\s*(\d+(?:\.\d+)?)\s*(mm)?", text, flags=re.I)
    if at_m:
        grade, dia, spc = at_m.group(1).upper(), float(at_m.group(2)), float(at_m.group(3))
        if target_template == "rc_pad_footing":
            explicit_dims.setdefault("mat_bar_dia_mm", dia)
            explicit_dims.setdefault("mat_spacing_mm", spc)
        elif target_template == "rc_slab":
            explicit_dims.setdefault("b1_dia_mm", dia)
            explicit_dims.setdefault("b1_spacing_mm", spc)
        elif target_template == "retaining_wall":
            explicit_dims.setdefault("s1_dia_mm", dia)
            explicit_dims.setdefault("s1_spacing_mm", spc)
        elif grade == "R":
            if target_template == "rc_column":
                explicit_dims.setdefault("tie_dia_mm", dia)
                explicit_dims.setdefault("tie_mid_spacing_mm", spc)
            elif target_template == "rc_beam":
                explicit_dims.setdefault("link_dia_mm", dia)
                explicit_dims.setdefault("link_mid_spacing_mm", spc)

    # Discrete bar callouts: 4xT20, 8 x T20, 3xT16
    cnt_m = re.search(r"\b(\d+)\s*[x×]\s*([TR])(\d{1,2})\b", text, flags=re.I)
    if cnt_m:
        cnt, dia = float(cnt_m.group(1)), float(cnt_m.group(3))
        if target_template == "rc_column":
            explicit_dims.setdefault("vert_bar_count", cnt)
            explicit_dims.setdefault("vert_bar_dia_mm", dia)
        elif target_template == "rc_beam":
            explicit_dims.setdefault("bot_bar_count", cnt)
            explicit_dims.setdefault("bot_bar_dia_mm", dia)
        elif target_template == "rc_pad_footing":
            explicit_dims.setdefault("dowel_count", cnt)
            explicit_dims.setdefault("dowel_dia_mm", dia)

    # Merge explicit metadata overrides if provided
    for k, v in meta.items():
        if isinstance(v, (int, float)):
            explicit_dims[str(k)] = float(v)

    required = TEMPLATE_REQUIRED_PARAMS.get(target_template or "", [])
    missing = [p for p in required if p not in explicit_dims]
    if target_template is None:
        ambiguities.append("Unable to determine target_template from brief.")

    questions = [f"Please confirm SI metric value for '{p}'." for p in missing]
    questions.extend(f"Resolve ambiguity: {a}" for a in ambiguities)

    ir = SketchIR(
        target_template=target_template,
        explicit_dimensions_mm=explicit_dims,
        inferred_constraints=inferred,
        missing_params=missing,
        ambiguities=ambiguities,
        needs_confirmation=bool(missing or ambiguities),
        confirmation_questions=questions,
    )
    return ir.model_dump()


def compile_ir_to_params(
    ir_payload: dict[str, Any],
    confirmed_updates: dict[str, Any] | None = None,
    fill_defaults: bool = False,
) -> dict[str, Any]:
    """Compile a SketchIR payload + confirmed updates into a recipe parameter dictionary."""
    target = ir_payload.get("target_template")
    params: dict[str, Any] = {}

    if fill_defaults and target:
        default_path = RECIPES_DIR / target / "params.json"
        if default_path.is_file():
            params.update(json.loads(default_path.read_text(encoding="utf-8")))

    for k, v in (ir_payload.get("explicit_dimensions_mm") or {}).items():
        if k in {"vert_bar_count", "bot_bar_count", "top_bar_count", "dowel_count"} or k.endswith("_dia_mm"):
            params[k] = int(round(float(v)))
        else:
            params[k] = float(v)

    if confirmed_updates:
        params.update(confirmed_updates)

    return params
