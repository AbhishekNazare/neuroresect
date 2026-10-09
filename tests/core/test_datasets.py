import hashlib
import io

import pytest
from neurocore import datasets
from neurocore.io import write_json


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


def manifest(tmp_path, body=b"verified research data"):
    value = {
        "schema_version": 1,
        "dataset_id": "test",
        "assets": [
            {
                "path": "data.bin",
                "url": "https://example.org/data",
                "size": len(body),
                "algorithm": "sha256",
                "digest": hashlib.sha256(body).hexdigest(),
            }
        ],
    }
    return write_json(tmp_path / "manifest.json", value), value


def test_inventory_does_not_treat_annex_pointers_as_downloaded_scans():
    tree = {
        "sha": datasets.IDEAS_COMMIT,
        "truncated": False,
        "tree": [
            {"path": "sub-1/ses-1/dwi/sub-1_ses-1_dwi.nii.gz", "type": "blob", "mode": "120000"},
            {"path": "sub-2/ses-1/anat/sub-2_ses-1_T1w.nii.gz", "type": "blob", "mode": "120000"},
        ],
    }
    report = datasets.ideas_inventory(tree)
    assert report["subject_count"] == 2
    assert report["modality_subject_counts"] == {"dwi": 1, "T1w": 1}
    assert report["training_ready_count"] == 0
    tree["truncated"] = True
    with pytest.raises(ValueError, match="complete pinned"):
        datasets.ideas_inventory(tree)


@pytest.mark.parametrize(
    "path", ["../escape", "/absolute", "a/../../escape", "a\\escape", "x.part", "."]
)
def test_manifest_rejects_unsafe_paths(tmp_path, path):
    _, value = manifest(tmp_path)
    value["assets"][0]["path"] = path
    with pytest.raises(ValueError):
        datasets.validate_manifest(value)


def test_download_verifies_and_reuses_local_bytes(tmp_path, monkeypatch):
    path, _ = manifest(tmp_path)
    calls = []

    def fetch(*args):
        calls.append(args)
        return Response(b"verified research data")

    monkeypatch.setattr(datasets, "_open", fetch)
    root = tmp_path / "raw"
    assert datasets.download_manifest(path, root)["files"][0]["status"] == "downloaded"
    assert datasets.download_manifest(path, root)["files"][0]["status"] == "already-verified"
    assert len(calls) == 1
    (root / "data.bin").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="Existing file fails checksum"):
        datasets.download_manifest(path, root)


@pytest.mark.parametrize("range_supported", [True, False])
def test_resume_or_restart_when_range_ignored(tmp_path, monkeypatch, range_supported):
    body = b"verified research data"
    path, _ = manifest(tmp_path, body)
    root = tmp_path / "raw"
    root.mkdir()
    (root / "data.bin.part").write_bytes(body[:5])

    def fetch(url, headers):
        assert headers["Range"] == "bytes=5-"
        return (
            Response(body[5:], 206, {"Content-Range": f"bytes 5-{len(body) - 1}/{len(body)}"})
            if range_supported
            else Response(body)
        )

    monkeypatch.setattr(datasets, "_open", fetch)
    datasets.download_manifest(path, root)
    assert (root / "data.bin").read_bytes() == body


@pytest.mark.parametrize(
    "status,body,error",
    [(202, b"", "HTTP 202"), (200, b"x" * 23, "exceeds"), (200, b"x" * 22, "checksum")],
)
def test_invalid_download_never_promoted(tmp_path, monkeypatch, status, body, error):
    path, _ = manifest(tmp_path)
    monkeypatch.setattr(datasets, "_open", lambda *args: Response(body, status))
    with pytest.raises(ValueError, match=error):
        datasets.download_manifest(path, tmp_path / "raw")
    assert not (tmp_path / "raw/data.bin").exists()


def test_budget_and_symlink_escape_fail_before_network(tmp_path, monkeypatch):
    path, _ = manifest(tmp_path)

    def no_network(*args):
        pytest.fail("must fail before network")

    monkeypatch.setattr(datasets, "_open", no_network)
    with pytest.raises(ValueError, match="budget"):
        datasets.download_manifest(path, tmp_path / "raw", max_bytes=1)
    root = tmp_path / "raw"
    root.mkdir()
    (root / "data.bin.part").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="symlinks"):
        datasets.download_manifest(path, root)


def test_cohort_audit_excludes_controls_missing_outcomes_and_identity_mismatch(
    tmp_path, line_connectome
):
    connectome = {
        **line_connectome,
        "synthetic": False,
        "dataset_id": "ideas-test",
        "patient_id": "sub-1",
        "actual_resection": [{"region_id": 1, "fraction_removed": 0.2}],
    }
    write_json(tmp_path / "connectome.json", connectome)
    patient = {
        "subject_id": "sub-1",
        "group": "surgical_patient",
        "outcome": 1,
        "followup_months": 12,
        "connectome": "connectome.json",
        "atlas_alignment_reviewed": True,
        "source_refs": ["fixture/source.csv:1"],
    }
    cohort = {
        "schema_version": 1,
        "dataset_id": "ideas-test",
        "endpoint": {"definition": "Test endpoint, not IDEAS mapping", "followup_months": 12},
        "subjects": [
            patient,
            {**patient, "subject_id": "sub-2", "outcome": None},
            {**patient, "subject_id": "sub-3", "group": "healthy_control"},
        ],
    }
    path = write_json(tmp_path / "cohort.json", cohort)
    report = datasets.audit_cohort(path)
    assert report["eligible_count"] == 1
    assert report["exclusion_counts"]["patient_id_mismatch"] == 2
    assert report["exclusion_counts"]["missing_outcome"] == 1
    assert report["class_counts"] == {"1": 1}
    cohort["subjects"].append(patient)
    write_json(path, cohort)
    with pytest.raises(ValueError, match="unique"):
        datasets.audit_cohort(path)
