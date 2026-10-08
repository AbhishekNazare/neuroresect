"""Portable JSON/CSV imports and strict JSON scientific artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from neurocore.validation import validate_connectome


def read_json(path: str | Path):
    def reject_constant(value):
        raise ValueError(f"Nonstandard JSON numeric constant: {value}")

    try:
        return json.loads(Path(path).read_text(), parse_constant=reject_constant)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read JSON artifact: {error}") from error


def write_json(path: str | Path, value) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return path


def import_connectome(path: str | Path, metadata_path: str | Path | None = None) -> dict:
    """CSV uses a square headerless matrix and a required JSON metadata sidecar.

    The sidecar supplies patient_id, atlas_id, dataset_id, nodes and optional
    actual_resection/synthetic. JSON input uses the complete connectome schema.
    No patient registration or database effects occur here.
    """
    path = Path(path)
    if path.suffix.lower() == ".csv":
        if metadata_path is None:
            raise ValueError("CSV imports require --metadata with nodes and dataset identifiers")
        metadata = read_json(metadata_path)
        if not isinstance(metadata, dict):
            raise ValueError("CSV metadata must be an object")
        try:
            matrix = np.loadtxt(path, delimiter=",")
        except (OSError, ValueError) as error:
            raise ValueError(f"Cannot read CSV matrix: {error}") from error
        return validate_connectome({**metadata, "matrix": matrix.tolist()})
    if metadata_path is not None:
        raise ValueError("A metadata sidecar is only supported for CSV imports")
    return validate_connectome(read_json(path))


def export_connectome(connectome: dict, path: str | Path) -> Path:
    return write_json(path, validate_connectome(connectome))
