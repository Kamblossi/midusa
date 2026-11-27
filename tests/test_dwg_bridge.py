"""Tests for AutoCAD .dxf <-> .dwg exchange bridge (engine/dwg_bridge.py & server.py)."""

from __future__ import annotations

from pathlib import Path
import sys

import ezdxf
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import engine  # noqa: F401
from engine.drafting_2d import Drafting2D
from engine.dwg_bridge import (
    SUPPORTED_DWG_VERSIONS,
    configure_odafc,
    dwg_to_dxf,
    dxf_to_dwg,
    find_oda_converter,
)
import server


def test_find_oda_converter_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_exe = tmp_path / "ODAFileConverter.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.setenv("MIDUSA_ODA_CONVERTER_PATH", str(fake_exe))
    assert find_oda_converter() == fake_exe


def test_configure_odafc_rejects_invalid_version() -> None:
    with pytest.raises(ValueError, match="Unsupported DWG version"):
        configure_odafc(version="ACAD1995")
    assert "ACAD2018" in SUPPORTED_DWG_VERSIONS


def test_configure_odafc_missing_oda_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIDUSA_ODA_CONVERTER_PATH", raising=False)
    monkeypatch.setattr("engine.dwg_bridge.find_oda_converter", lambda: None)
    with pytest.raises(RuntimeError, match="ODAFileConverter.exe not found"):
        configure_odafc("ACAD2018")


def test_dxf_to_dwg_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        dxf_to_dwg(tmp_path / "nonexistent.dxf")


def test_mcp_server_registers_dwg_tools() -> None:
    assert hasattr(server, "export_dwg")
    assert hasattr(server, "import_dwg")


@pytest.mark.skipif(
    find_oda_converter() is None,
    reason="ODAFileConverter.exe not installed on host; skipping live DWG round-trip test",
)
def test_dxf_dwg_dxf_metric_roundtrip(tmp_path: Path) -> None:
    draft = Drafting2D()
    draft.add_rectangle(0.0, 0.0, 2400.0, 2400.0, layer="CONCRETE_OUTLINE")
    draft.add_line((75.0, 150.0), (2325.0, 150.0), layer="REBAR_MAIN")
    dxf_in = draft.save_dxf(tmp_path / "pad_in.dxf")

    dwg_res = dxf_to_dwg(dxf_in, tmp_path / "pad_out.dwg", version="ACAD2018")
    assert Path(dwg_res["dwg_path"]).is_file()
    assert dwg_res["size_bytes"] > 0

    dxf_res = dwg_to_dxf(dwg_res["dwg_path"], tmp_path / "pad_roundtrip.dxf")
    assert dxf_res["insunits"] == 4
    assert "CONCRETE_OUTLINE" in dxf_res["layers"]
    assert "REBAR_MAIN" in dxf_res["layers"]
    rt_doc = ezdxf.readfile(dxf_res["dxf_path"])
    assert rt_doc.header["$INSUNITS"] == 4
    assert len(rt_doc.audit().errors) == 0
