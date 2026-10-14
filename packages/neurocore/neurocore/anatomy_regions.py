"""Join named connectome regions to explicit FreeSurfer voxel IDs and audit fractions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel.affines import apply_affine
from nibabel.processing import resample_from_to

from neurocore.anatomy import audit, audit_volumes
from neurocore.ideas_cohort import canonical_label

ALIASES = {"Left-Thalamus": "Left-Thalamus-Proper", "Right-Thalamus": "Right-Thalamus-Proper"}


def load_volume(path: Path) -> nib.spatialimages.SpatialImage:
    image = nib.load(path)
    if not isinstance(image, nib.spatialimages.SpatialImage):
        raise ValueError("Expected a spatial image")
    return image


def label_mapping(labels: list[str], lut_text: str) -> list[dict]:
    if len(labels) != 82 or len(set(labels)) != 82:
        raise ValueError("Expected 82 unique connectome labels in source order")
    candidates: dict[str, dict] = {}
    for line in lut_text.splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if len(fields) < 6:
            raise ValueError("Malformed FreeSurfer label table")
        name = ALIASES.get(fields[1], canonical_label(fields[1]))
        if name not in labels:
            continue
        identifier = int(fields[0])
        color = list(map(int, fields[2:5]))
        if name in candidates or identifier <= 0 or any(not 0 <= value <= 255 for value in color):
            raise ValueError("Ambiguous or invalid atlas label definition")
        candidates[name] = {
            "label": name,
            "source_label": fields[1],
            "voxel_id": identifier,
            "color_rgb": color,
        }
    if set(candidates) != set(labels):
        raise ValueError("FreeSurfer table does not cover every connectome label")
    rows = [{"index": index, **candidates[label]} for index, label in enumerate(labels)]
    if len({row["voxel_id"] for row in rows}) != 82:
        raise ValueError("Multiple connectome regions map to the same voxel ID")
    return rows


def measure_regions(atlas, mask, mapping: list[dict]) -> list[dict]:
    """Both volumes must already share a checked, millimetre coordinate grid."""
    audit_volumes(atlas, mask, atlas, atlas)
    labels = np.asarray(atlas.dataobj)
    resected = np.asarray(mask.dataobj) > 0
    volume = abs(float(np.linalg.det(atlas.affine[:3, :3])))
    rows = []
    for row in mapping:
        selected = labels == row["voxel_id"]
        count = int(selected.sum())
        if count == 0:
            raise ValueError(f"Atlas region has no voxels: {row['label']}")
        overlap = int(np.count_nonzero(selected & resected))
        center = apply_affine(atlas.affine, np.array(np.where(selected)).mean(axis=1))
        rows.append(
            {
                **row,
                "voxel_count": count,
                "volume_mm3": count * volume,
                "centroid_scanner_ras_mm": center.tolist(),
                "resected_voxels": overlap,
                "resection_fraction": overlap / count,
            }
        )
    return rows


def compare_fractions(rows: list[dict], published: list[float]) -> dict:
    expected = np.asarray(published, dtype=float)
    if (
        expected.shape != (len(rows),)
        or not np.isfinite(expected).all()
        or np.any((expected < 0) | (expected > 1))
    ):
        raise ValueError("Published fractions must match the region count and lie within [0,1]")
    measured = np.array([row["resection_fraction"] for row in rows])
    errors = measured - expected
    return {
        "mean_absolute_difference": float(np.abs(errors).mean()),
        "max_absolute_difference": float(np.abs(errors).max()),
        "rows": [
            {
                **row,
                "published_fraction": float(expected[index]),
                "difference": float(errors[index]),
            }
            for index, row in enumerate(rows)
        ],
    }


def report(root: Path, cohort_path: Path, lut_path: Path, subject_id: str) -> dict:
    cohort = json.loads(cohort_path.read_text())
    if cohort["atlas"] != "Lausanne-36" or cohort["resection_input_unit"] != "fraction":
        raise ValueError("This audit requires a Lausanne-36 cohort with explicit fraction inputs")
    subjects = [row for row in cohort["subjects"] if row["subject_id"] == subject_id]
    if len(subjects) != 1 or not subjects[0]["eligible"]:
        raise ValueError("Expected one eligible cohort record for the selected subject")
    geometry = audit(root, subject_id)
    mapping = label_mapping(cohort["region_labels"], lut_path.read_text())
    mask = load_volume(root / "resection.nii.gz")
    native = load_volume(root / "mri/rawavg.mgz")
    reference = load_volume(root / "mri/T1.mgz")
    paths = {"cohort": cohort_path, "lut": lut_path}
    comparisons = {}
    for name in ("myaparc_36", "aparc+aseg"):
        path = root / f"mri/{name}.mgz"
        paths[name] = path
        atlas = load_volume(path)
        audit_volumes(native, mask, reference, atlas)
        conformed_mask = resample_from_to(mask, (atlas.shape, atlas.affine), order=0)
        native_atlas = resample_from_to(atlas, (mask.shape, mask.affine), order=0)
        for space, image, region_mask in (
            ("conformed", atlas, conformed_mask),
            ("native", native_atlas, mask),
        ):
            # Resampling MGH produces NIfTI with default unknown units; the target's
            # checked millimetre grid is known here, so record it explicitly.
            for resampled in (image, region_mask):
                if hasattr(resampled.header, "set_xyzt_units"):
                    resampled.header.set_xyzt_units("mm")
            rows = measure_regions(image, region_mask, mapping)
            comparisons[f"{name}:{space}"] = compare_fractions(
                rows, subjects[0]["resection_fractions"]
            )
    return {
        "format": "neuroresect-anatomy-regions-v1",
        "subject_id": subject_id,
        "geometry": geometry,
        "mapping": mapping,
        "mapping_method": "Exact names from supplied FreeSurfer LUT with two explicit thalamus aliases",
        "mapping_verified_against_supplied_lut": True,
        "comparisons": comparisons,
        "source_hashes": {
            key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()
        },
        "published_fractions_reproduced": False,
        "clinical_use_validated": False,
        "limitations": [
            "Numeric label/name correspondence is not proof of spatial registration accuracy.",
            "Both grids use nearest-neighbour resampling; no new registration is estimated.",
            "Published fractions remain unchanged; differences require source-method review.",
            "A close match in one subject does not independently confirm cohort-wide resection units.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--lut", required=True, type=Path)
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = report(args.directory, args.cohort, args.lut, args.subject_id)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Mapped 82 regions; comparisons written to {args.output}")


if __name__ == "__main__":
    main()
