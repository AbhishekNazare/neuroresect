import io
import zipfile

import pytest
from neurocore.cli import main
from neurocore.ideas import (
    checked_members,
    index_network_archive,
    parse_matrix_member,
    prepare_network_archives,
    read_network_matrix,
)

NAME = (
    "probabilistic_tractography/Lausanne-125/sub-445/ses-2/dwi/"
    "sub-445_ses-2_Probabilistic-Tractography_125-Lausanne_Count.csv"
)


def zip_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def test_actual_source_path_convention():
    row = parse_matrix_member(NAME)
    assert row["subject_id"] == "sub-445"
    assert row["atlas"] == "Lausanne-125"
    with pytest.raises(ValueError, match="subject/session"):
        parse_matrix_member(NAME.replace("/sub-445/", "/sub-446/"))
    with pytest.raises(ValueError, match="atlas identifiers"):
        parse_matrix_member(NAME.replace("/Lausanne-125/", "/Lausanne-60/"))


def test_nested_acquisition_inventory_and_reuse(tmp_path):
    source = tmp_path / "networks.zip"
    nested = zip_bytes([(NAME, b"0,2\n2,0\n"), ("__MACOSX/metadata", b"ignored")])
    source.write_bytes(
        zip_bytes(
            [
                ("networks/probabilistic_tractography.zip", nested),
                (
                    "networks/deterministic_tractography.zip",
                    zip_bytes([("readme.txt", b"unknown")]),
                ),
            ]
        )
    )
    cache = tmp_path / "cache"
    first = prepare_network_archives(source, cache)
    child = cache / "probabilistic_tractography.zip"
    before = child.stat().st_mtime_ns
    assert prepare_network_archives(source, cache) == first
    assert child.stat().st_mtime_ns == before
    inventory = index_network_archive(child)
    assert inventory["matrix_count"] == 1
    assert inventory["subject_count"] == 1
    assert inventory["missing_combination_count"] == 4
    assert inventory["unrecognized_members"] == []
    matrix = read_network_matrix(child, NAME)
    assert matrix["matrix"] == [[0, 2], [2, 0]]
    assert matrix["synthetic"] is False
    assert matrix["anatomical_mapping_verified"] is False
    assert "nodes" not in matrix
    child.write_bytes(b"corrupt cache")
    prepare_network_archives(source, cache)
    assert read_network_matrix(child, NAME)["region_count"] == 2


@pytest.mark.parametrize("name", ["../outside.csv", "/absolute.csv", "a\\b.csv"])
def test_unsafe_members_rejected(tmp_path, name):
    path = tmp_path / "bad.zip"
    path.write_bytes(zip_bytes([(name, b"0")]))
    with zipfile.ZipFile(path) as archive, pytest.raises(ValueError, match="Unsafe"):
        checked_members(archive)


def test_measures_remain_distinct_and_invalid_matrices_fail(tmp_path):
    path = tmp_path / "networks.zip"
    md_name = NAME.replace("_Count.csv", "_MeanMD.csv")
    path.write_bytes(zip_bytes([(md_name, b"0,0.001\n0.001,0\n")]))
    assert read_network_matrix(path, md_name)["strength_weight_candidate"] is False
    path.write_bytes(zip_bytes([(NAME, b"0,2\n1,0\n")]))
    with pytest.raises(ValueError, match="symmetric"):
        read_network_matrix(path, NAME)


def test_matrix_cli_and_invalid_zip(tmp_path, capsys):
    path = tmp_path / "networks.zip"
    path.write_bytes(zip_bytes([(NAME, b"0,2\n2,0\n")]))
    assert (
        main(
            ["ideas-matrix", str(path), "--member", NAME, "--output", str(tmp_path / "matrix.json")]
        )
        == 0
    )
    assert "anatomical_mapping_verified" in capsys.readouterr().out
    path.write_bytes(b"not a zip")
    assert (
        main(
            ["ideas-matrix", str(path), "--member", NAME, "--output", str(tmp_path / "matrix.json")]
        )
        == 2
    )


def test_batch_audit_retains_failures_and_disconnected_regions(tmp_path):
    from neurocore.ideas import audit_network_matrices

    path = tmp_path / "networks.zip"
    other = NAME.replace("sub-445", "sub-446")
    path.write_bytes(zip_bytes([(NAME, b"0,0\n0,0\n"), (other, b"0,2\n1,0\n")]))
    report = audit_network_matrices(path, "Lausanne-125")
    assert report["valid_count"] == 1
    assert report["invalid_count"] == 1
    assert report["matrices"][0]["isolated_regions"] == 2
    assert "symmetric" in report["matrices"][1]["error"]
    with pytest.raises(ValueError, match="No matrices"):
        audit_network_matrices(path, "absent-atlas")
