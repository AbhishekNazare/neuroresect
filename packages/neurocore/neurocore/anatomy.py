"""Audit native-mask and FreeSurfer geometry without claiming image registration."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np
from nibabel.affines import apply_affine
from nibabel.processing import resample_from_to

ATOL = 1e-4  # millimetres; accommodates serialized header rounding, not misregistration.


def check_volume(image):
    affine = image.affine
    if (
        len(image.shape) != 3
        or not np.isfinite(affine).all()
        or not np.allclose(affine[3], [0, 0, 0, 1], atol=ATOL, rtol=0)
        or abs(np.linalg.det(affine[:3, :3])) < 1e-8
    ):
        raise ValueError("Expected a 3D volume with a finite, invertible spatial affine")


def same_grid(first, second):
    check_volume(first)
    check_volume(second)
    return first.shape == second.shape and np.allclose(
        first.affine, second.affine, atol=ATOL, rtol=0
    )


def audit_volumes(native, mask, reference, atlas):
    for image in (native, mask, reference, atlas):
        check_volume(image)
        if hasattr(image.header, "get_xyzt_units") and image.header.get_xyzt_units()[0] != "mm":
            raise ValueError("NIfTI spatial units must explicitly be millimetres")
    if not same_grid(native, mask):
        raise ValueError("Resection mask does not match the native MRI grid")
    if not same_grid(reference, atlas):
        raise ValueError("Parcellation does not match the conformed MRI grid")
    values = np.asarray(mask.dataobj)
    if not np.isin(values, [0, 1]).all() or not np.any(values):
        raise ValueError("Resection mask must be nonempty and binary")
    labels = np.asarray(atlas.dataobj)
    if not np.isfinite(labels).all() or np.any(labels < 0) or np.any(labels != np.floor(labels)):
        raise ValueError("Parcellation must contain nonnegative integer labels")
    # This uses supplied scanner geometry; it does not estimate a registration.
    mapped = resample_from_to(mask, (reference.shape, reference.affine), order=0)
    mapped_values = np.asarray(mapped.dataobj) > 0
    if not np.any(mapped_values):
        raise ValueError("Mask has no voxels in the conformed reference field of view")
    voxel_volume = abs(float(np.linalg.det(mask.affine[:3, :3])))
    mapped_volume = int(mapped_values.sum()) * abs(float(np.linalg.det(reference.affine[:3, :3])))
    original_volume = int(values.sum()) * voxel_volume
    return {
        "native_grid_matches_mask": True,
        "conformed_grid_matches_atlas": True,
        "native_shape": list(map(int, native.shape)),
        "conformed_shape": list(map(int, reference.shape)),
        "native_affine": native.affine.tolist(),
        "conformed_affine": reference.affine.tolist(),
        "native_mask_voxels": int(values.sum()),
        "native_mask_volume_mm3": original_volume,
        "conformed_mask_voxels": int(mapped_values.sum()),
        "resampled_volume_relative_change": (mapped_volume - original_volume) / original_volume,
        "mask_fraction_inside_nonzero_parcellation": float(np.mean(labels[mapped_values] > 0)),
        "mask_to_conformed_voxels": (np.linalg.inv(reference.affine) @ mask.affine).tolist(),
        "resampling": "nearest-neighbour using supplied scanner affines; no registration estimated",
    }


def surface_to_scanner(reference, metadata):
    """Require the surface's embedded source geometry to match the reference."""
    check_volume(reference)
    if not str(metadata.get("valid", "")).startswith("1"):
        raise ValueError("Surface lacks valid embedded volume geometry")
    try:
        dimensions = np.asarray(metadata["volume"])
        basis = np.column_stack([metadata[k] for k in ("xras", "yras", "zras")])
        basis = basis @ np.diag(metadata["voxelsize"])
        affine = np.eye(4)
        affine[:3, :3] = basis
        affine[:3, 3] = np.asarray(metadata["cras"]) - basis @ (dimensions / 2)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Incomplete surface volume geometry") from exc
    if tuple(dimensions) != reference.shape or not np.allclose(
        affine, reference.affine, atol=ATOL, rtol=0
    ):
        raise ValueError("Surface source geometry differs from the conformed MRI")
    return reference.affine @ np.linalg.inv(reference.header.get_vox2ras_tkr())


def audit(root: Path, subject_id: str):
    paths = {
        "native": root / "mri/rawavg.mgz",
        "mask": root / "resection.nii.gz",
        "reference": root / "mri/T1.mgz",
        "atlas": root / "mri/myaparc_36.mgz",
    }
    images = {key: nib.load(path) for key, path in paths.items()}
    result = audit_volumes(**images)
    surfaces = {}
    for hemisphere in ("lh", "rh"):
        path = root / f"surf/{hemisphere}.pial"
        paths[hemisphere] = path
        vertices, faces, metadata = nib.freesurfer.read_geometry(path, read_metadata=True)
        if (
            vertices.ndim != 2
            or vertices.shape[1] != 3
            or len(vertices) == 0
            or not np.isfinite(vertices).all()
            or faces.ndim != 2
            or faces.shape[1] != 3
            or len(faces) == 0
            or faces.min() < 0
            or faces.max() >= len(vertices)
        ):
            raise ValueError("Invalid surface vertices or triangle indices")
        transform = surface_to_scanner(images["reference"], metadata)
        world = apply_affine(transform, vertices)
        surfaces[hemisphere] = {
            "vertices": len(vertices),
            "triangles": len(faces),
            "surface_ras_to_scanner_ras": transform.tolist(),
            "scanner_bounds_mm": [world.min(axis=0).tolist(), world.max(axis=0).tolist()],
        }
    return {
        "format": "neuroresect-anatomy-audit-v1",
        "subject_id": subject_id,
        "subject_id_source": "caller-supplied; verify against archive and cohort provenance",
        "geometry": result,
        "surfaces": surfaces,
        "inputs": {
            key: {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for key, path in paths.items()
        },
        "visual_alignment_review_required": True,
        "connectome_label_mapping_verified": False,
        "regional_resection_units_verified": False,
        "limitations": [
            "Matching headers establish coordinate compatibility, not anatomical accuracy.",
            "Inspect image overlays before enabling physical resection or patient inference.",
            "Surface and voxel label IDs have not been joined to connectome ordering.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.directory, args.subject_id)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Geometry audit saved to {args.output}; visual and label-order review remain required.")


if __name__ == "__main__":
    main()
