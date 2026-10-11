import csv
import io
import zipfile

import numpy as np
import pytest
from neurocore.ideas_cohort import (
    build_ideas_cohort,
    canonical_label,
    map_outcome,
    read_resections,
    read_subject_table,
)
from openpyxl import Workbook


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        csv.writer(stream).writerows(rows)
    return path


def test_duplicate_rows_are_audited_but_conflicts_fail(tmp_path):
    path = write_csv(tmp_path / "patients.csv", [["ID", "Sex"], ["209", "F"], ["209", "F"]])
    records, duplicates = read_subject_table(path)
    assert len(records) == 1 and duplicates == ["sub-209"]
    write_csv(path, [["ID", "Sex"], ["209", "F"], ["209", "M"]])
    with pytest.raises(ValueError, match="Conflicting"):
        read_subject_table(path)


def test_outcomes_and_name_mapping_are_explicit():
    assert map_outcome("1") == 1
    assert map_outcome("2") == 0
    assert map_outcome("NA") is None
    with pytest.raises(ValueError):
        map_outcome("7")
    assert canonical_label("'ctx-lh-insula'") == "l.insula"
    assert canonical_label("'Right-Caudate'") == "Right-Caudate"


def test_resections_join_by_label_and_preserve_missingness(tmp_path):
    path = write_csv(
        tmp_path / "resection.csv",
        [["", "1", "2"], ["'ctx-rh-insula'", 0.2, "NaN"], ["'ctx-lh-insula'", 0.4, 0.6]],
    )
    result = read_resections(path, ["l.insula", "r.insula"], "fraction")
    assert result["sub-1"] == [0.4, 0.2]
    assert result["sub-2"] is None
    with pytest.raises(ValueError, match="do not match"):
        read_resections(path, ["l.other", "r.insula"], "fraction")
    write_csv(path, [["", "1"], ["l.insula", 25], ["r.insula", 50]])
    assert read_resections(path, ["l.insula", "r.insula"], "percent")["sub-1"] == [0.25, 0.5]
    with pytest.raises(ValueError, match="within"):
        read_resections(path, ["l.insula", "r.insula"], "fraction")


def test_source_join_excludes_controls_and_keeps_age_categories(tmp_path):
    patients = write_csv(
        tmp_path / "patients.csv",
        [
            ["ID", "Sex", "Binned_Onset_Age", "Binned_Age_at_Scan", "Number_ASMs", "ILAE_Year1"],
            ["1", "F", "5 to 7", "30 to 34", "2", "1"],
        ],
    )
    controls = write_csv(tmp_path / "controls.csv", [["ID", "Sex"], ["4001", "M"]])
    labels = [f"Left-test{i}" for i in range(82)]
    book = Workbook()
    book.active.title = "scale36"
    for label in labels:
        book.active.append([label])
    atlas = tmp_path / "labels.xlsx"
    book.save(atlas)
    resections = write_csv(
        tmp_path / "resections.csv",
        [["", "1"]] + [[label, 0.5 if i == 0 else 0] for i, label in enumerate(labels)],
    )
    archive = tmp_path / "networks.zip"
    matrix = io.StringIO()
    np.savetxt(matrix, np.ones((82, 82)) - np.eye(82), delimiter=",")
    with zipfile.ZipFile(archive, "w") as z:
        for identifier in ("1", "4001"):
            name = f"probabilistic_tractography/Lausanne-36/sub-{identifier}/ses-1/dwi/sub-{identifier}_ses-1_Probabilistic-Tractography_36-Lausanne_Count.csv"
            z.writestr(name, matrix.getvalue())
    result = build_ideas_cohort(
        patients, controls, atlas, resections, archive, tmp_path / "cohort.json", "fraction"
    )
    assert result["eligible_count"] == 1
    assert result["network_group_counts"] == {"surgical_patient": 1, "healthy_control": 1}
    assert result["subjects"][0]["clinical"]["Binned_Onset_Age"] == "5 to 7"
    assert result["subjects"][1]["target"] is None
    assert result["anatomical_coordinates_available"] is False
