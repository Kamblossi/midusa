"""Midusa CAD Engine — core 2D/3D parametric geometry, drafting, rendering, and workspace tools.

CRITICAL: ``usd_brep`` is imported first so the ``omniSolid`` USD schema registers
before any ``pxr`` module is loaded.
"""

import usd_brep  # noqa: F401 — must precede any pxr import

from engine.drafting_2d import Drafting2D
from engine.dwg_bridge import (
    DwgBridge,
    configure_odafc,
    dwg_to_dxf,
    dxf_to_dwg,
    find_oda_converter,
)
from engine.member_profiles import (
    solve_flanged_profile,
    solve_pad_footing_profile,
    solve_rect_profile,
    solve_retaining_wall_profile,
    solve_slab_profile,
)
from engine.rebar_detailing import (
    BarScheduleItem,
    build_bar_bending_schedule,
    build_bbs_table,
    calc_ld_tension,
    calc_ldc_compression,
    calc_ldh_hook,
    calc_lsc_compression_lap,
    compute_bar_distribution,
    compute_takeoff,
    cut_length_mm,
    distribute_bars,
    distribute_discrete_bars,
    distribute_multi_zone,
    min_bend_dia,
    standard_bend_diameter_mm,
    standard_hook_extension_mm,
    standard_hook_leg_90_mm,
    total_schedule_mass_kg,
)
from engine.renderer import Renderer3D
from engine.repair_loop import run_bounded_repair
from engine.sketch_bridge import SketchBridge
from engine.sketch_ir import SketchIR, compile_ir_to_params, parse_sketch_brief
from engine.solid_3d import Solid3DBuilder
from engine.workspace import WorkspaceManager

__all__ = [
    "BarScheduleItem",
    "Drafting2D",
    "DwgBridge",
    "Renderer3D",
    "SketchBridge",
    "SketchIR",
    "Solid3DBuilder",
    "WorkspaceManager",
    "compile_ir_to_params",
    "parse_sketch_brief",
    "run_bounded_repair",
    "build_bar_bending_schedule",
    "build_bbs_table",
    "calc_ld_tension",
    "calc_ldc_compression",
    "calc_ldh_hook",
    "calc_lsc_compression_lap",
    "compute_bar_distribution",
    "compute_takeoff",
    "configure_odafc",
    "cut_length_mm",
    "distribute_bars",
    "distribute_discrete_bars",
    "distribute_multi_zone",
    "dwg_to_dxf",
    "dxf_to_dwg",
    "find_oda_converter",
    "min_bend_dia",
    "solve_flanged_profile",
    "solve_pad_footing_profile",
    "solve_rect_profile",
    "solve_retaining_wall_profile",
    "solve_slab_profile",
    "standard_bend_diameter_mm",
    "standard_hook_extension_mm",
    "standard_hook_leg_90_mm",
    "total_schedule_mass_kg",
]
