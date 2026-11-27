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
        self.doc.header["$INSUNITS"] = 4
        self.doc.header["$MEASUREMENT"] = 1
        self.doc.header["$LWDISPLAY"] = 1
        self.msp = self.doc.modelspace()
        self._setup_layers()

    def _setup_layers(self) -> None:
        layers = self.doc.layers
        layer_defs = [
            # Mechanical / general layers (Phase 1)
            ("OUTLINE", 7, "Continuous", 35),
            ("HOLES", 4, "Continuous", 25),
            ("TEXT", 2, "Continuous", 18),
            # Standard 16 Structural & Civil CAD layers (Primitive 5)
            ("CONCRETE_OUTLINE", 7, "Continuous", 35),
            ("CONCRETE_HIDDEN", 8, "DASHED", 18),
            ("CONCRETE_HATCH", 9, "Continuous", 13),
            ("BLINDING", 252, "Continuous", 25),
            ("SOIL_GROUND", 30, "DASHED", 25),
            ("REBAR_MAIN", 1, "Continuous", 50),
            ("REBAR_SECONDARY", 3, "Continuous", 35),
            ("REBAR_DOWELS", 6, "Continuous", 50),
            ("REBAR_LINKS", 4, "Continuous", 30),
            ("REBAR_TIES", 4, "Continuous", 30),  # alias for REBAR_LINKS
            ("CENTERLINES", 2, "CENTER", 15),
            ("GRIDLINES", 5, "CENTER", 18),
            ("DIMENSIONS", 2, "Continuous", 18),
            ("TEXT_NOTES", 7, "Continuous", 18),
            ("CALLOUTS", 6, "Continuous", 25),
            ("SCHEDULE_GRID", 7, "Continuous", 25),
            ("TITLE_BLOCK", 7, "Continuous", 50),
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

    def add_hidden_rectangle(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        layer: str = "CONCRETE_HIDDEN",
    ) -> None:
        self.add_rectangle(x, y, width, height, layer=layer)

    def add_concrete_hatch(
        self,
        points: list[tuple[float, float]],
        pattern: str = "AR-CONC",
        scale: float = 8.0,
        color: int = 8,
        layer: str = "CONCRETE_OUTLINE",
    ) -> None:
        hatch = self.msp.add_hatch(color=color, dxfattribs={"layer": layer})
        try:
            hatch.set_pattern_fill(pattern, scale=scale)
        except Exception:
            hatch.set_pattern_fill("ANSI31", scale=scale)
        hatch.paths.add_polyline_path(points, is_closed=True)

    def add_hooked_rebar_polyline(
        self,
        points: list[tuple[float, float]],
        width: float = 10.0,
        layer: str = "REBAR_MAIN",
    ) -> None:
        self.msp.add_lwpolyline(
            points,
            format="xy",
            dxfattribs={"layer": layer, "const_width": width},
        )

    def add_text_note(
        self,
        text: str,
        insert: tuple[float, float],
        height: float = 45.0,
        layer: str = "TEXT_NOTES",
    ) -> None:
        self.msp.add_text(text, height=height, dxfattribs={"layer": layer, "insert": insert})

    def add_section_callout(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
        label: str = "A",
        text_height: float = 60.0,
        layer: str = "TEXT_NOTES",
    ) -> None:
        self.msp.add_line(p1, p2, dxfattribs={"layer": "CENTERLINES"})
        self.add_text_note(label, (p1[0] - text_height * 1.1, p1[1] - text_height * 0.4), height=text_height, layer=layer)
        self.add_text_note(label, (p2[0] + text_height * 0.4, p2[1] - text_height * 0.4), height=text_height, layer=layer)

    def add_north_arrow(
        self,
        origin: tuple[float, float],
        size: float = 180.0,
        layer: str = "TEXT_NOTES",
    ) -> None:
        x, y = origin
        self.msp.add_line((x, y), (x, y + size), dxfattribs={"layer": layer})
        self.msp.add_line((x, y + size), (x - size * 0.22, y + size * 0.65), dxfattribs={"layer": layer})
        self.msp.add_line((x, y + size), (x + size * 0.22, y + size * 0.65), dxfattribs={"layer": layer})
        self.add_text_note("N", (x - size * 0.14, y + size * 1.1), height=size * 0.35, layer=layer)

    def add_bbs_table(
        self,
        origin: tuple[float, float],
        rows: list[dict],
        title: str = "BAR BENDING SCHEDULE (METRIC - mm / kg)",
        row_height: float = 90.0,
        text_height: float = 32.0,
        layer: str = "SCHEDULE_GRID",
    ) -> None:
        """Draw a clean tabular Bar Bending Schedule block on the DXF modelspace."""
        x0, y0 = origin
        headers = [
            ("Mark", 260.0),
            ("Type/Size", 320.0),
            ("No. Off", 260.0),
            ("Spacing (mm)", 360.0),
            ("Cut Length (mm)", 420.0),
            ("Total Mass (kg)", 400.0),
        ]
        total_w = sum(w for _, w in headers)
        total_rows = len(rows) + 2  # header + data + total

        # Title
        self.add_text_note(title, (x0, y0 + 35.0), height=text_height * 1.25, layer="TEXT_NOTES")

        # Horizontal grid lines
        for r in range(total_rows + 1):
            yr = y0 - r * row_height
            self.msp.add_line((x0, yr), (x0 + total_w, yr), dxfattribs={"layer": layer})

        # Vertical grid lines & headers
        cx = x0
        for col_title, col_w in headers:
            self.msp.add_line((cx, y0), (cx, y0 - total_rows * row_height), dxfattribs={"layer": layer})
            self.add_text_note(
                col_title,
                (cx + 18.0, y0 - row_height * 0.65),
                height=text_height,
                layer="TEXT_NOTES",
            )
            cx += col_w
        self.msp.add_line((x0 + total_w, y0), (x0 + total_w, y0 - total_rows * row_height), dxfattribs={"layer": layer})

        # Data rows
        total_mass = 0.0
        for idx, row in enumerate(rows, start=1):
            yr = y0 - idx * row_height - row_height * 0.65
            spacing_str = f"{int(round(row['spacing_mm']))}" if row.get("spacing_mm") else "-"
            vals = [
                str(row["mark"]),
                str(row["type_size"]),
                str(row["no_off"]),
                spacing_str,
                f"{int(round(row['cut_length_mm']))}",
                f"{row['total_mass_kg']:.2f}",
            ]
            total_mass += float(row["total_mass_kg"])
            cx = x0
            for val, (_, col_w) in zip(vals, headers):
                self.add_text_note(val, (cx + 18.0, yr), height=text_height, layer="TEXT_NOTES")
                cx += col_w

        # Total row
        yr_tot = y0 - (len(rows) + 1) * row_height - row_height * 0.65
        self.add_text_note("TOTAL STEEL MASS", (x0 + 18.0, yr_tot), height=text_height, layer="TEXT_NOTES")
        mass_x = x0 + sum(w for _, w in headers[:-1]) + 18.0
        self.add_text_note(f"{total_mass:.2f} kg", (mass_x, yr_tot), height=text_height, layer="TEXT_NOTES")

    def save_dxf(self, path: str | Path) -> Path:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        auditor = self.doc.audit()
        if auditor.errors:
            raise RuntimeError(f"DXF audit failed with {len(auditor.errors)} errors: {auditor.errors}")
        self.doc.saveas(str(out_path))
        return out_path

    def export_dxf_and_png(
        self,
        dxf_path: str | Path,
        png_path: str | Path,
        dpi: int = 200,
    ) -> tuple[Path, Path]:
        return self.save_dxf(dxf_path), self.export_png(png_path, dpi=dpi)

    def draw_bbs_table(
        self,
        origin: tuple[float, float],
        rows: list[dict],
        title: str = "BAR BENDING SCHEDULE (METRIC - mm / kg)",
    ) -> None:
        self.add_bbs_table(origin, rows, title=title)

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
