import nibabel as nib
import numpy as np
import pytest
from neurocore.anatomy_regions import compare_fractions, label_mapping, measure_regions


def definitions():
    labels = [f"l.region_{index}" for index in range(82)]
    table = "\n".join(f"{1000 + index} ctx-lh-region_{index} 10 20 30 0" for index in range(82))
    return labels, table


def test_mapping_preserves_connectome_order_not_lut_order():
    labels, table = definitions()
    rows = label_mapping(list(reversed(labels)), table)
    assert rows[0]["index"] == 0
    assert rows[0]["voxel_id"] == 1081
    assert rows[-1]["label"] == labels[0]


def test_explicit_thalamus_alias():
    labels, table = definitions()
    labels[0] = "Left-Thalamus-Proper"
    table = table.replace("1000 ctx-lh-region_0", "10 Left-Thalamus")
    assert label_mapping(labels, table)[0]["voxel_id"] == 10


@pytest.mark.parametrize("change", ["missing", "duplicate_name", "duplicate_id", "invalid_color"])
def test_invalid_mapping_is_rejected(change):
    labels, table = definitions()
    if change == "missing":
        table = "\n".join(table.splitlines()[1:])
    elif change == "duplicate_name":
        table += "\n1000 ctx-lh-region_0 10 20 30 0"
    elif change == "duplicate_id":
        table = table.replace("1001 ctx-lh-region_1", "1000 ctx-lh-region_1")
    else:
        table = table.replace("10 20 30", "999 20 30")
    with pytest.raises(ValueError):
        label_mapping(labels, table)


def volumes():
    affine = np.diag([2.0, 3.0, 4.0, 1.0])
    affine[:3, 3] = [10, 20, 30]
    labels = np.zeros((4, 4, 4), dtype=np.int16)
    labels[0:2, 0:2, 0:2] = 10
    labels[2:4, 2:4, 2:4] = 20
    mask = np.zeros_like(labels)
    mask[0, 0:2, 0:2] = 1
    images = [nib.Nifti1Image(v, affine) for v in (labels, mask)]
    for img in images:
        img.header.set_xyzt_units("mm")
    return images


def test_physical_centroid_volume_and_fraction():
    atlas, mask = volumes()
    mapping = [{"label": "a", "voxel_id": 10}, {"label": "b", "voxel_id": 20}]
    rows = measure_regions(atlas, mask, mapping)
    assert rows[0]["volume_mm3"] == pytest.approx(192)
    assert rows[0]["resection_fraction"] == 0.5
    assert rows[1]["resection_fraction"] == 0
    assert rows[0]["centroid_scanner_ras_mm"] == [11, 21.5, 32]
    comparison = compare_fractions(rows, [0.4, 0.1])
    assert comparison["mean_absolute_difference"] == pytest.approx(0.1)
    assert comparison["rows"][0]["published_fraction"] == 0.4
    assert rows[0]["resection_fraction"] == 0.5


def test_missing_region_fails_instead_of_inventing_centroid():
    with pytest.raises(ValueError, match="no voxels"):
        measure_regions(*volumes(), [{"label": "absent", "voxel_id": 999}])


@pytest.mark.parametrize("values", [[0.1], [np.nan, 0.5], [-0.1, 0.5], [1.1, 0.5]])
def test_invalid_published_fractions_rejected(values):
    with pytest.raises(ValueError):
        compare_fractions([{"resection_fraction": 0.5}, {"resection_fraction": 0}], values)
