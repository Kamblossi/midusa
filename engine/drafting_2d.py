"""2D CAD drafting and PNG export wrapping ezdxf."""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf import units
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib
import matplotlib.pyplot as plt

matplotlib.use("Agg")


class Drafting2D:
    """Creates layered 2D technical drawings in DXF and renders them to PNG."""

    def __init__(self, doc_units: int = units.MM) -> None:
        self.doc = ezdxf.new("R2010", setup=True)
        self.doc.units = doc_units
        self.msp = self.doc.modelspace()
        self._setup_layers()

    def _setup_layers(self) -> None:
        layers = self.doc.layers
        layer_defs = [
            ("OUTLINE", 7, "Continuous", 35),
            ("HOLES", 4, "Continuous", 25),
            ("CENTERLINES", 1, "CENTER", 13),
            ("DIMENSIONS", 3, "Continuous", 18),
            ("TEXT", 2, "Continuous", 18),
        ]
        for name, color, linetype, lineweight in layer_defs:
            if name not in layers:
                lt = linetype if linetype in self.doc.linetypes else "Continuous"
                layers.add(
                    name,
                    color=color,
                    linetype=lt,
                    lineweight=lineweight,
                )

    def add_line(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        layer: str = "OUTLINE",
    ) -> None:
        self.msp.add_line(p1, p2, dxfattribs={"layer": layer})

    def add_rectangle(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        layer: str = "OUTLINE",
    ) -> None:
        pts = [
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
        ]
        self.msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})

    def add_circle(
        self,
        cx: float,
        cy: float,
        radius: float,
        layer: str = "HOLES",
        with_centerlines: bool = True,
    ) -> None:
        self.msp.add_circle((cx, cy), radius=radius, dxfattribs={"layer": layer})
        if with_centerlines:
            ext = radius * 1.4
            self.add_line((cx - ext, cy), (cx + ext, cy), layer="CENTERLINES")
            self.add_line((cx, cy - ext), (cx, cy + ext), layer="CENTERLINES")

    def add_linear_dim(
        self,
        base: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        angle: float = 0.0,
        text_height: float = 5.0,
        layer: str = "DIMENSIONS",
    ) -> None:
        dim = self.msp.add_linear_dim(
            base=base,
            p1=p1,
            p2=p2,
            angle=angle,
            dimstyle="EZDXF",
            override={"dimtxt": text_height, "dimasz": text_height * 0.6},
            dxfattribs={"layer": layer},
        )
        dim.render()

    def add_diameter_dim(
        self,
        center: tuple[float, float],
        radius: float,
        angle: float = 45.0,
        text_height: float = 4.5,
        layer: str = "DIMENSIONS",
    ) -> None:
        dim = self.msp.add_diameter_dim(
            center=center,
            radius=radius,
            angle=angle,
            dimstyle="EZDXF",
            override={"dimtxt": text_height, "dimasz": text_height * 0.6},
            dxfattribs={"layer": layer},
        )
        dim.render()

    def add_title_block(
        self,
        title: str,
        subtitle: str = "",
        origin: tuple[float, float] = (0.0, -35.0),
        text_height: float = 6.0,
    ) -> None:
        x, y = origin
        self.msp.add_text(
            title,
            height=text_height,
            dxfattribs={"layer": "TEXT", "insert": (x, y)},
        )
        if subtitle:
            self.msp.add_text(
                subtitle,
                height=text_height * 0.65,
                dxfattribs={"layer": "TEXT", "insert": (x, y - text_height * 1.4)},
            )

    def save_dxf(self, path: str | Path) -> Path:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.saveas(str(out_path))
        return out_path

    def export_png(
        self,
        path: str | Path,
        dpi: int = 200,
        bg_color: str = "#111827",
    ) -> Path:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        fig = plt.figure(figsize=(10, 8), dpi=dpi)
        ax = fig.add_axes([0.05, 0.05, 0.9, 0.9])
        ctx = RenderContext(self.doc)
        cfg = Configuration(
            background_policy=BackgroundPolicy.CUSTOM,
            custom_bg_color=bg_color,
            color_policy=ColorPolicy.COLOR,
        )
        backend = MatplotlibBackend(ax)
        Frontend(ctx, backend, config=cfg).draw_layout(self.msp, finalize=True)
        fig.savefig(str(out_path), dpi=dpi, facecolor=bg_color)
        plt.close(fig)
        return out_path
