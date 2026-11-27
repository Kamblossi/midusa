"""Midusa CAD Engine — core 2D/3D parametric geometry, drafting, rendering, and workspace tools.

CRITICAL: ``usd_brep`` is imported first so the ``omniSolid`` USD schema registers
before any ``pxr`` module is loaded.
"""

import usd_brep  # noqa: F401 — must precede any pxr import

from engine.drafting_2d import Drafting2D
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
from engine.sketch_bridge import SketchBridge
from engine.solid_3d import Solid3DBuilder
from engine.workspace import WorkspaceManager

__all__ = [
    "BarScheduleItem",
    "Drafting2D",
    "Renderer3D",
    "SketchBridge",
    "Solid3DBuilder",
    "WorkspaceManager",
    "build_bar_bending_schedule",
    "build_bbs_table",
    "calc_ld_tension",
    "calc_ldc_compression",
    "calc_ldh_hook",
    "calc_lsc_compression_lap",
    "compute_bar_distribution",
    "compute_takeoff",
    "cut_length_mm",
    "distribute_bars",
    "distribute_discrete_bars",
    "distribute_multi_zone",
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
