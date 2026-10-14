import nibabel as nib
import numpy as np
import pytest
from neurocore.anatomy import audit_volumes, surface_to_scanner


def volumes():
    affine = np.eye(4)
    native = nib.Nifti1Image(np.ones((8, 8, 8), dtype=np.uint8), affine)
    values = np.zeros((8, 8, 8), dtype=np.uint8)
    values[2:4, 2:4, 2:4] = 1
    mask = nib.Nifti1Image(values, affine)
    return native, mask, native, native


def test_volume_audit_preserves_identity_mask():
    result = audit_volumes(*volumes())
    assert result["native_mask_volume_mm3"] == 8
    assert result["conformed_mask_voxels"] == 8
    assert result["resampled_volume_relative_change"] == 0
    assert result["mask_fraction_inside_nonzero_parcellation"] == 1


def test_same_shape_shifted_mask_is_rejected():
    native, mask, reference, atlas = volumes()
    shifted = np.eye(4)
    shifted[0, 3] = 1
    mask = nib.Nifti1Image(np.asarray(mask.dataobj), shifted)
    with pytest.raises(ValueError, match="native MRI grid"):
        audit_volumes(native, mask, reference, atlas)


@pytest.mark.parametrize("value", [0, 0.5, np.nan, 2])
def test_empty_or_invalid_mask_is_rejected(value):
    native, mask, reference, atlas = volumes()
    mask = nib.Nifti1Image(np.full(mask.shape, value, dtype=float), np.eye(4))
    with pytest.raises(ValueError, match="nonempty and binary"):
        audit_volumes(native, mask, reference, atlas)


def test_disjoint_conformed_grid_is_rejected():
    native, mask, reference, atlas = volumes()
    affine = np.eye(4)
    affine[0, 3] = 100
    reference = nib.Nifti1Image(np.asarray(reference.dataobj), affine)
    with pytest.raises(ValueError, match="field of view"):
        audit_volumes(native, mask, reference, reference)


def test_nearest_neighbour_uses_world_coordinates():
    native, mask, reference, atlas = volumes()
    affine = np.eye(4)
    affine[0, 3] = 1
    reference = nib.Nifti1Image(np.asarray(reference.dataobj), affine)
    result = audit_volumes(native, mask, reference, reference)
    assert result["conformed_mask_voxels"] == 8
    assert result["mask_to_conformed_voxels"][0][3] == -1


def test_surface_transform_and_embedded_geometry():
    affine = np.diag([2.0, 3.0, 4.0, 1.0])
    affine[:3, 3] = [10, 20, 30]
    image = nib.MGHImage(np.zeros((8, 10, 12), dtype=np.float32), affine)
    metadata = {
        "valid": "1",
        "volume": [8, 10, 12],
        "voxelsize": [2, 3, 4],
        "xras": [1, 0, 0],
        "yras": [0, 1, 0],
        "zras": [0, 0, 1],
        "cras": [18, 35, 54],
    }
    transform = surface_to_scanner(image, metadata)
    voxel = np.array([1.0, 2.0, 3.0, 1.0])
    np.testing.assert_allclose(transform @ image.header.get_vox2ras_tkr() @ voxel, affine @ voxel)
    metadata["cras"] = [18, 35, 55]
    with pytest.raises(ValueError, match="differs"):
        surface_to_scanner(image, metadata)
    with pytest.raises(ValueError, match="lacks valid"):
        surface_to_scanner(image, {})
