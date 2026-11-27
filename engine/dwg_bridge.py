"""AutoCAD .dxf <-> .dwg exchange bridge wrapping ezdxf.addons.odafc (SI metric mm)."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any

import ezdxf
from ezdxf.addons import odafc

SUPPORTED_DWG_VERSIONS = (
    "ACAD2000",
    "ACAD2004",
    "ACAD2007",
    "ACAD2010",
    "ACAD2013",
    "ACAD2018",
)


def find_oda_converter() -> Path | None:
    """Locate ODAFileConverter.exe via env var, standard Windows ODA folders, or PATH."""
    env_path = os.environ.get("MIDUSA_ODA_CONVERTER_PATH", "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return candidate

    oda_roots = (
        Path(r"C:\Program Files\ODA"),
        Path(r"C:\Program Files (x86)\ODA"),
    )
    for root in oda_roots:
        if root.is_dir():
            for match in sorted(root.rglob("ODAFileConverter.exe")):
                if match.is_file():
                    return match

    which_path = shutil.which("ODAFileConverter") or shutil.which("ODAFileConverter.exe")
    if which_path:
        return Path(which_path)

    return None


def configure_odafc(version: str = "ACAD2018") -> Path:
    """Validate DWG version, locate ODAFileConverter.exe, and configure ezdxf.addons.odafc."""
    if version not in SUPPORTED_DWG_VERSIONS:
        raise ValueError(
            f"Unsupported DWG version '{version}'. Supported: {', '.join(SUPPORTED_DWG_VERSIONS)}"
        )

    exe_path = find_oda_converter()
    if exe_path is None:
        raise RuntimeError(
            "ODAFileConverter.exe not found. Install the free Open Design Alliance (ODA) "
            "File Converter (https://www.opendesign.com/guestfiles/oda_file_converter) into "
            r"'C:\Program Files\ODA' or set MIDUSA_ODA_CONVERTER_PATH to the executable path."
        )

    odafc.win_exec_path = str(exe_path)
    odafc.default_version = version
    return exe_path


def dxf_to_dwg(
    dxf_path: str | Path,
    dwg_path: str | Path | None = None,
    version: str = "ACAD2018",
) -> dict[str, Any]:
    """Audit an SI metric .dxf and convert it to AutoCAD .dwg via ODA File Converter."""
    src = Path(dxf_path)
    if not src.is_file():
        raise FileNotFoundError(f"Source DXF file not found: {src}")

    doc = ezdxf.readfile(str(src))
    auditor = doc.audit()
    if auditor.errors:
        raise RuntimeError(f"DXF audit failed with {len(auditor.errors)} errors: {auditor.errors}")

    configure_odafc(version=version)

    out_dwg = Path(dwg_path) if dwg_path is not None else src.with_suffix(".dwg")
    out_dwg.parent.mkdir(parents=True, exist_ok=True)
    odafc.export_dwg(doc, str(out_dwg), version=version, replace=True)

    if not out_dwg.is_file() or out_dwg.stat().st_size == 0:
        raise RuntimeError(f"ODA conversion produced missing or empty DWG file: {out_dwg}")

    return {
        "dwg_path": str(out_dwg),
        "version": version,
        "size_bytes": out_dwg.stat().st_size,
        "layer_count": len(doc.layers),
    }


def dwg_to_dxf(
    dwg_path: str | Path,
    dxf_path: str | Path | None = None,
) -> dict[str, Any]:
    """Read an AutoCAD .dwg via ODA File Converter, enforce SI metric mm units, audit, and save .dxf."""
    src = Path(dwg_path)
    if not src.is_file():
        raise FileNotFoundError(f"Source DWG file not found: {src}")

    configure_odafc()

    doc = odafc.readfile(str(src))
    doc.header["$INSUNITS"] = 4
    doc.header["$MEASUREMENT"] = 1

    auditor = doc.audit()
    if auditor.errors:
        raise RuntimeError(f"Converted DXF audit failed with {len(auditor.errors)} errors: {auditor.errors}")

    out_dxf = Path(dxf_path) if dxf_path is not None else src.with_suffix(".dxf")
    out_dxf.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(out_dxf))

    return {
        "dxf_path": str(out_dxf),
        "insunits": int(doc.header["$INSUNITS"]),
        "layers": [layer.dxf.name for layer in doc.layers],
        "entity_count": len(doc.modelspace()),
    }


class DwgBridge:
    """Class facade for AutoCAD .dxf <-> .dwg exchange."""

    find_oda_converter = staticmethod(find_oda_converter)
    configure_odafc = staticmethod(configure_odafc)
    dxf_to_dwg = staticmethod(dxf_to_dwg)
    dwg_to_dxf = staticmethod(dwg_to_dxf)
