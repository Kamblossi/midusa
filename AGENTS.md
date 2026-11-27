# Midusa â€” Autonomous CAD Agent Instructions

## Project Identity & Environment
- **Project Name:** Midusa
- **Local Workspace:** `C:\Users\ADMIN\MySoftware\Midusa`
- **GitHub Repository:** `https://github.com/Kamblossi/midusa.git`
- **Git Author:** `Kamblossi <newton.ochieng97@gmail.com>`
- **Python Environment:** Always use `C:\Users\ADMIN\MySoftware\Midusa\.venv\Scripts\python.exe` (CPython 3.12).
- **Execution Mode:** Run commands autonomously without asking for confirmation on routine file edits, dependency installs, test runs, `git add`, `git commit`, or `git push`. Only pause if a command fails repeatedly after bounded retries or an external system/API requires human input.

## Continuous Git & GitHub Workflow
- Initialize or verify `git` in `C:\Users\ADMIN\MySoftware\Midusa` with:
  - `git config user.name "Kamblossi"`
  - `git config user.email "newton.ochieng97@gmail.com"`
  - `remote.origin.url` set to `https://github.com/Kamblossi/midusa.git`
- Never store secrets, tokens, or credentials inside committed source files. If a `.env` or local config exists, ensure it is listed in `.gitignore`.
- Commit logically after each completed module or milestone with clear commit messages (e.g., `feat(engine): add PlaneGCS SketchBridge and ezdxf drafting`), and push immediately to `origin main` (`git push -u origin main`).
- Ensure `workspaces/` outputs, temporary render artifacts, `.venv/`, `__pycache__/`, and build caches are properly ignored in `.gitignore` while keeping source code, tests, benchmark scripts, and `Dockerfile` / `pyproject.toml` tracked.

## Finalized Architecture & Stack Invariants
We are building an open-source, self-hostable AI CAD drafting agent patterned on the `classcad-ai` agent loop (`run_script`, visual/numeric verification, checkpoints/restore, and MCP), tailored for multi-discipline technical drawings (mechanical, structural, civil, electrical) with rough sketch-to-IR and strict code-compliance layers in upcoming phases.

Use these exact libraries for the core engine:
1. **3D NURBS / B-Rep Kernel:** NVIDIA `usd-brep` (`pip install usd-brep`, Apache 2.0, SMLib).
   - **Critical rule:** Always `import usd_brep` *before* importing `pxr` or opening any OpenUSD stage so the `omniSolid` schema registers.
   - **Ownership rule:** `boolean_difference(A, B)` consumes operands unless `keep_other_brep=True` is passed; `circular_fillet` mutates in place and requires `8e-5 <= r <= min_adjacent_face_dim / 3`.
2. **2D Constraint Solver:** FreeCAD's `PlaneGCS` (`pip install planegcs`, LGPL) to solve 2D parametric constraints (`DOF == 0` check).
3. **2D Drafting & DXF:** `ezdxf` (`pip install ezdxf`, MIT) for layers, linetypes, dimensions, and 2D rendering via `ezdxf.addons.drawing`.
4. **Headless Visual & Diff Verification:** `pyvista` (VTK), `pillow`, and `scikit-image` (SSIM + amplified visual diff between checkpoints).
5. **Agent Harness & MCP:** `fastmcp` with a **Script-as-Feature-Tree** model (`params.json` + `build.py` + versioned `checkpoints/v{N}/` snapshots and rollback).

## Phase 1 Build & Verification Tasks (Start Here First)
Build and verify Phase 1 locally before tackling Phase 2 (discipline recipes + AutoCAD `.dwg`/MCP bridge) or Phase 3 (two-stage Sketch-to-IR + RASE code-compliance engine):
1. Create `.gitignore`, `pyproject.toml`, and `Dockerfile` (CPython 3.12).
2. Implement:
   - `engine/__init__.py` (`import usd_brep` first)
   - `engine/sketch_bridge.py` (`SketchBridge` wrapping `planegcs`)
   - `engine/drafting_2d.py` (`Drafting2D` wrapping `ezdxf` + 2D PNG export)
   - `engine/solid_3d.py` (`Solid3DBuilder` wrapping `usd_brep` + `assert_valid`, bounding box, USD export, tessellation)
   - `engine/renderer.py` (`PyVista` multi-angle renders + `Pillow`/`scikit-image` SSIM & diff images)
   - `engine/workspace.py` (`WorkspaceManager` for `params.json` + `build.py` + `checkpoints/v{N}` + `restore`)
   - `server.py` (`FastMCP` tools: `run_script`, `update_params`, `restore_checkpoint`)
3. Create and run `examples/baseplate_build.py` using `.venv\Scripts\python.exe` to generate `v1` (M16 holes) and `v2` (M20 holes) with `.dxf`, `.usd`, multi-angle PNGs, and visual diff outputs.
4. Fix any real API or runtime errors encountered during execution, verify all outputs exist, and push the working Phase 1 codebase to `https://github.com/Kamblossi/midusa.git` (`main`).