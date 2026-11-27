"""Script-as-Feature-Tree workspace manager with versioned checkpoints and rollback."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


class WorkspaceManager:
    """Manages ``params.json``, ``build.py``, and versioned ``checkpoints/v{N}/`` snapshots."""

    def __init__(self, workspace_dir: str | Path) -> None:
        self.root = Path(workspace_dir).resolve()
        self.params_path = self.root / "params.json"
        self.build_path = self.root / "build.py"
        self.checkpoints_dir = self.root / "checkpoints"
        self.root.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def init_workspace(self, params: dict[str, Any], build_script: str) -> None:
        self.params_path.write_text(json.dumps(params, indent=2), encoding="utf-8")
        self.build_path.write_text(build_script, encoding="utf-8")

    def get_params(self) -> dict[str, Any]:
        if not self.params_path.exists():
            return {}
        return json.loads(self.params_path.read_text(encoding="utf-8"))

    def update_params(self, updates: dict[str, Any]) -> dict[str, Any]:
        params = self.get_params()
        params.update(updates)
        self.params_path.write_text(json.dumps(params, indent=2), encoding="utf-8")
        return params

    def list_checkpoints(self) -> list[int]:
        versions: list[int] = []
        for entry in self.checkpoints_dir.iterdir():
            if entry.is_dir() and entry.name.startswith("v"):
                suffix = entry.name[1:]
                if suffix.isdigit():
                    versions.append(int(suffix))
        return sorted(versions)

    def _next_version(self) -> int:
        versions = self.list_checkpoints()
        return (versions[-1] + 1) if versions else 1

    def run_build(
        self,
        script_code: str | None = None,
        python_exe: str | None = None,
    ) -> dict[str, Any]:
        """Execute ``build.py`` and snapshot outputs into ``checkpoints/v{N}/``."""
        if script_code is not None:
            self.build_path.write_text(script_code, encoding="utf-8")
        if not self.build_path.exists():
            raise FileNotFoundError(f"Missing build script: {self.build_path}")

        exe = python_exe or sys.executable
        env = os.environ.copy()
        env["MIDUSA_WORKSPACE"] = str(self.root)

        proc = subprocess.run(
            [exe, str(self.build_path)],
            cwd=str(self.root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"build.py failed (exit {proc.returncode}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )

        version = self._next_version()
        ckpt_dir = self.checkpoints_dir / f"v{version}"
        ckpt_dir.mkdir(parents=True, exist_ok=True)

        copied_files: list[str] = []
        for item in self.root.iterdir():
            if item.name == "checkpoints":
                continue
            dest = ckpt_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
            copied_files.append(item.name)

        return {
            "version": version,
            "checkpoint_dir": str(ckpt_dir),
            "files": sorted(copied_files),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    def restore_checkpoint(self, version: int) -> dict[str, Any]:
        """Restore ``params.json``, ``build.py``, and artifacts from ``checkpoints/v{version}/``."""
        ckpt_dir = self.checkpoints_dir / f"v{version}"
        if not ckpt_dir.exists():
            raise FileNotFoundError(f"Checkpoint v{version} not found at {ckpt_dir}")

        for item in self.root.iterdir():
            if item.name == "checkpoints":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        restored_files: list[str] = []
        for item in ckpt_dir.iterdir():
            dest = self.root / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
            restored_files.append(item.name)

        return {
            "restored_version": version,
            "workspace": str(self.root),
            "files": sorted(restored_files),
        }
