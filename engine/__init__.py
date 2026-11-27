"""Midusa CAD Engine — core 2D/3D parametric geometry, drafting, rendering, and workspace tools.

CRITICAL: ``usd_brep`` is imported first so the ``omniSolid`` USD schema registers
before any ``pxr`` module is loaded.
"""

import usd_brep  # noqa: F401 — must precede any pxr import

from engine.drafting_2d import Drafting2D
from engine.renderer import Renderer3D
from engine.sketch_bridge import SketchBridge
from engine.solid_3d import Solid3DBuilder
from engine.workspace import WorkspaceManager

__all__ = [
    "Drafting2D",
    "Renderer3D",
    "SketchBridge",
    "Solid3DBuilder",
    "WorkspaceManager",
]
