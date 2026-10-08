"""Canonical, portable provenance: scientific hashes exclude runtime metadata."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from neurocore import __version__


def content_hash(value: Any) -> str:
    """Hash strict canonical JSON, independent of mapping insertion order."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def code_revision() -> str:
    revision = os.environ.get("NEURORESECT_GIT_COMMIT")
    if revision:
        return revision
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent,
            stderr=subprocess.DEVNULL, text=True, timeout=2,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def provenance(operation: str, inputs: Any, config: dict | None = None) -> dict:
    versions = {}
    for package in ("numpy", "scipy", "networkx", "scikit-learn"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unavailable"
    return {
        "engine_version": __version__, "operation": operation,
        "code_revision": code_revision(), "code_dirty": code_dirty(), "python_version": platform.python_version(),
        "dependencies": versions, "input_hash": content_hash(inputs),
        "config_hash": content_hash(config or {}), "config": config or {},
        "research_only": True,
    }


def connectome_identity(connectome: dict) -> dict:
    return {key: connectome[key] for key in (
        "patient_id", "dataset_id", "atlas_id", "synthetic", "nodes", "matrix"
    )}


def code_dirty() -> bool | None:
    try:
        return bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=Path(__file__).parent,
            stderr=subprocess.DEVNULL, text=True, timeout=2,
        ).strip())
    except (OSError, subprocess.SubprocessError):
        return None
