"""Headless 3D multi-angle rendering (PyVista) and visual diffing (Pillow + scikit-image)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import pyvista as pv
from skimage.metrics import structural_similarity as ssim
import usd_brep


class Renderer3D:
    """Renders ``usd_brep.Brep`` solids to multi-angle PNGs and computes SSIM visual diffs."""

    DEFAULT_VIEWS = ("iso", "top", "front", "side")

    @staticmethod
    def brep_to_polydata(
        brep: usd_brep.Brep,
        chord_height_tolerance: float = 0.01,
    ) -> pv.PolyData:
        poly = usd_brep.tessellate(brep, chord_height_tolerance=chord_height_tolerance)
        arrays = poly.to_numpy_arrays()
        mesh = pv.PolyData(arrays["points"], arrays["faces"])
        mesh = mesh.compute_normals(auto_orient_normals=True, consistent_normals=True)
        return mesh

    def render_views(
        self,
        brep: usd_brep.Brep,
        output_dir: str | Path,
        prefix: str = "view",
        views: tuple[str, ...] | list[str] | None = None,
        window_size: tuple[int, int] = (1024, 768),
        chord_height_tolerance: float = 0.01,
    ) -> dict[str, Path]:
        """Render multi-angle PNGs of a Brep solid using off-screen PyVista."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        mesh = self.brep_to_polydata(brep, chord_height_tolerance=chord_height_tolerance)
        view_list = list(views or self.DEFAULT_VIEWS)
        rendered: dict[str, Path] = {}

        for view_name in view_list:
            plotter = pv.Plotter(off_screen=True, window_size=window_size)
            plotter.set_background("#0f172a", top="#1e293b")
            plotter.add_mesh(
                mesh,
                color="#94a3b8",
                metallic=0.35,
                roughness=0.45,
                show_edges=True,
                edge_color="#334155",
                line_width=0.6,
            )
            plotter.add_axes()

            if view_name == "iso":
                plotter.view_isometric()
            elif view_name == "top":
                plotter.view_xy()
            elif view_name == "front":
                plotter.view_xz()
            elif view_name == "side":
                plotter.view_yz()
            else:
                plotter.view_isometric()

            plotter.reset_camera()
            out_path = out_dir / f"{prefix}_{view_name}.png"
            plotter.screenshot(str(out_path))
            plotter.close()
            rendered[view_name] = out_path

        return rendered

    @staticmethod
    def compute_visual_diff(
        img_a_path: str | Path,
        img_b_path: str | Path,
        diff_out_path: str | Path,
        amplify: float = 6.0,
    ) -> dict[str, Any]:
        """Compute SSIM between two PNGs and save an amplified visual diff overlay."""
        img_a = Image.open(img_a_path).convert("RGB")
        img_b = Image.open(img_b_path).convert("RGB")
        if img_a.size != img_b.size:
            img_b = img_b.resize(img_a.size, Image.Resampling.BILINEAR)

        arr_a = np.asarray(img_a, dtype=np.float32) / 255.0
        arr_b = np.asarray(img_b, dtype=np.float32) / 255.0

        score = float(ssim(arr_a, arr_b, channel_axis=-1, data_range=1.0))

        abs_diff = np.abs(arr_a - arr_b)
        max_channel_diff = np.max(abs_diff, axis=-1)
        changed_pct = float(np.mean(max_channel_diff > 0.02) * 100.0)

        # Build amplified diff visualization: dimmed grayscale base + bright red/magenta delta
        gray_base = np.mean(arr_b, axis=-1, keepdims=True) * 0.35
        amp = np.clip(max_channel_diff * amplify, 0.0, 1.0)[..., None]
        highlight = np.concatenate([amp, np.zeros_like(amp), amp * 0.4], axis=-1)
        vis = np.clip(gray_base + highlight, 0.0, 1.0)
        vis_img = Image.fromarray((vis * 255.0).astype(np.uint8), mode="RGB")

        out_path = Path(diff_out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        vis_img.save(str(out_path))

        return {
            "ssim": round(score, 6),
            "changed_pixels_pct": round(changed_pct, 3),
            "diff_path": str(out_path),
        }
