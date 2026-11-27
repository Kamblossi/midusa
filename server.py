"""Midusa FastMCP server exposing script execution, parameter updates, and checkpoint rollback."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

import engine  # noqa: F401 — ensures usd_brep loads before any pxr usage
from engine.dwg_bridge import dwg_to_dxf, dxf_to_dwg
from engine.workspace import WorkspaceManager

mcp = FastMCP("midusa")


@mcp.tool()
def run_script(
    workspace_dir: str,
    script_code: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write/update ``build.py`` (and optional ``params.json``), execute it, and create a checkpoint."""
    wm = WorkspaceManager(workspace_dir)
    if params is not None:
        wm.update_params(params)
    return wm.run_build(script_code=script_code)


@mcp.tool()
def update_params(
    workspace_dir: str,
    updates: dict[str, Any],
    rebuild: bool = True,
) -> dict[str, Any]:
    """Update ``params.json`` in a workspace and optionally re-run ``build.py`` to create a new checkpoint."""
    wm = WorkspaceManager(workspace_dir)
    new_params = wm.update_params(updates)
    result: dict[str, Any] = {"params": new_params}
    if rebuild:
        result["build"] = wm.run_build()
    return result


@mcp.tool()
def restore_checkpoint(workspace_dir: str, version: int) -> dict[str, Any]:
    """Restore a workspace to a previously saved ``checkpoints/v{version}/`` snapshot."""
    wm = WorkspaceManager(workspace_dir)
    return wm.restore_checkpoint(version)


@mcp.tool()
def export_dwg(
    dxf_path: str,
    dwg_path: str | None = None,
    version: str = "ACAD2018",
) -> dict[str, Any]:
    """Convert an audited SI metric .dxf drawing to AutoCAD .dwg via ODA File Converter."""
    return dxf_to_dwg(dxf_path, dwg_path=dwg_path, version=version)


@mcp.tool()
def import_dwg(
    dwg_path: str,
    dxf_path: str | None = None,
) -> dict[str, Any]:
    """Import an AutoCAD .dwg drawing into an audited SI metric (mm, $INSUNITS=4) .dxf."""
    return dwg_to_dxf(dwg_path, dxf_path=dxf_path)


if __name__ == "__main__":
    mcp.run()
