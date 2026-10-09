"""Pinned dataset inventories and bounded, verified acquisition (no implicit extraction)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from neurocore.io import read_json, write_json

IDEAS_COMMIT = "2e7f2573a5f8a9921cb19fca5e601bc141633f49"
IDEAS_REPOSITORY = "OpenNeuroDatasets/ds007401"


def _open(url: str, headers: dict | None = None):
    if urlparse(url).scheme != "https":
        raise ValueError("Dataset downloads require HTTPS")
    return urlopen(
        Request(url, headers={"User-Agent": "NeuroResect/0.2", **(headers or {})}), timeout=60
    )


def _relative_path(value: str) -> Path:
    path = PurePosixPath(value)
    if not value or not path.parts or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("Asset paths must be relative and cannot traverse directories")
    if str(path) != value or value.endswith(".part"):
        raise ValueError("Asset paths must be canonical and cannot end in .part")
    return Path(*path.parts)


def _digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new("sha1" if algorithm == "git-blob-sha1" else algorithm)
    if algorithm == "git-blob-sha1":
        digest.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_manifest(manifest: dict) -> list[dict]:
    if manifest.get("schema_version") != 1 or not manifest.get("dataset_id"):
        raise ValueError("Expected a version 1 dataset manifest with dataset_id")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("Manifest must contain assets")
    seen = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("Each asset must be an object")
        path = str(_relative_path(asset.get("path", "")))
        if path == "acquisition-report.json" or path in seen:
            raise ValueError(f"Duplicate asset path: {path}")
        seen.add(path)
        size = asset.get("size")
        if type(size) is not int or size < 0:
            raise ValueError("Asset size must be a nonnegative integer")
        if urlparse(asset.get("url", "")).scheme != "https":
            raise ValueError("Asset URL must use HTTPS")
        algorithm = asset.get("algorithm", "")
        length = {"sha256": 64, "md5": 32, "git-blob-sha1": 40}.get(algorithm)
        if length is None or not re.fullmatch(f"[0-9a-f]{{{length}}}", asset.get("digest", "")):
            raise ValueError("Asset must have a valid source checksum")
    return assets


def ideas_inventory(tree: dict) -> dict:
    """Inventory lists source availability, never infers diagnoses or outcomes from IDs."""
    if tree.get("truncated") is not False or tree.get("sha") != IDEAS_COMMIT:
        raise ValueError("Expected the complete pinned IDEAS II Git tree")
    subjects: dict[str, dict] = {}
    for entry in tree["tree"]:
        path = entry["path"]
        if entry["type"] != "blob" or not path.startswith("sub-"):
            continue
        subject = path.split("/")[0]
        row = subjects.setdefault(subject, {"subject_id": subject, "files": [], "modalities": []})
        row["files"].append(path)
        for suffix, modality in (
            ("_dwi.nii.gz", "dwi"),
            ("_T1w.nii.gz", "T1w"),
            ("_FLAIR.nii.gz", "FLAIR"),
        ):
            if path.endswith(suffix) and modality not in row["modalities"]:
                row["modalities"].append(modality)
    counts = Counter(modality for row in subjects.values() for modality in row["modalities"])
    return {
        "schema_version": 1,
        "dataset_id": "openneuro-ds007401-1.0.0",
        "source_commit": IDEAS_COMMIT,
        "subjects": sorted(subjects.values(), key=lambda row: row["subject_id"]),
        "subject_count": len(subjects),
        "modality_subject_counts": dict(counts),
        "training_ready_count": 0,
        "limitations": [
            "Inventory is source availability, not downloaded scan data.",
            "OpenNeuro contains raw imaging, not the Figshare connectomes or outcome tables.",
            "Patient/control status and surgical outcome are not inferred from subject IDs.",
        ],
    }


def discover_ideas(output: str | Path, subjects: list[str] | None = None) -> dict:
    """Download release inventory and create a small metadata-only acquisition manifest."""
    with _open(
        f"https://api.github.com/repos/{IDEAS_REPOSITORY}/git/trees/{IDEAS_COMMIT}?recursive=1"
    ) as response:
        if response.status != 200:
            raise ValueError(f"Inventory request returned HTTP {response.status}")
        tree = json.load(response)
    inventory = ideas_inventory(tree)
    selected = set(subjects or ["sub-1"])
    known = {row["subject_id"] for row in inventory["subjects"]}
    if not selected <= known:
        raise ValueError(f"Unknown subjects: {sorted(selected - known)}")
    assets = []
    for entry in tree["tree"]:
        path = entry["path"]
        root_metadata = path in ("README.md", "CHANGES", "dataset_description.json")
        sidecar = path.split("/")[0] in selected and path.endswith((".json", ".bval", ".bvec"))
        if entry["type"] == "blob" and entry["mode"] == "100644" and (root_metadata or sidecar):
            assets.append(
                {
                    "path": path,
                    "size": entry["size"],
                    "algorithm": "git-blob-sha1",
                    "digest": entry["sha"],
                    "url": f"https://raw.githubusercontent.com/"
                    f"{IDEAS_REPOSITORY}/{IDEAS_COMMIT}/{path}",
                }
            )
    manifest = {
        "schema_version": 1,
        "dataset_id": inventory["dataset_id"],
        "source_commit": IDEAS_COMMIT,
        "scope": "metadata-only",
        "assets": assets,
    }
    validate_manifest(manifest)
    write_json(Path(output) / "inventory.json", inventory)
    write_json(Path(output) / "source-tree.json", tree)
    write_json(Path(output) / "manifest.json", manifest)
    return {
        "inventory": str(Path(output) / "inventory.json"),
        "manifest": str(Path(output) / "manifest.json"),
        "subject_count": inventory["subject_count"],
        "modality_subject_counts": inventory["modality_subject_counts"],
        "download_bytes": sum(asset["size"] for asset in assets),
        "scope": "metadata-only",
    }


def download_manifest(
    manifest_path: str | Path, destination: str | Path, max_bytes: int = 100_000_000
) -> dict:
    manifest = read_json(manifest_path)
    assets = validate_manifest(manifest)
    total = sum(asset["size"] for asset in assets)
    if max_bytes < 0 or total > max_bytes:
        raise ValueError(f"Manifest requires {total} bytes, exceeding budget {max_bytes}")
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < total:
        raise ValueError("Insufficient free disk space for this manifest")
    results = []
    for asset in assets:
        target = root / _relative_path(asset["path"])
        partial = target.with_name(target.name + ".part")
        for candidate in (target, partial):
            if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
                raise ValueError("Asset destination must not escape root through symlinks")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if (
                target.stat().st_size != asset["size"]
                or _digest(target, asset["algorithm"]) != asset["digest"]
            ):
                raise ValueError(f"Existing file fails checksum: {asset['path']}")
            status = "already-verified"
        else:
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > asset["size"]:
                raise ValueError(f"Partial file is larger than source: {asset['path']}")
            if offset < asset["size"] or not partial.exists():
                headers = {"Range": f"bytes={offset}-"} if offset else {}
                with _open(asset["url"], headers) as response:
                    if response.status not in (200, 206):
                        raise ValueError(
                            f"Download returned HTTP {response.status}; provider may require browser access"
                        )
                    if response.status == 206:
                        expected = f"bytes {offset}-{asset['size'] - 1}/{asset['size']}"
                        if response.headers.get("Content-Range") != expected:
                            raise ValueError("Invalid Content-Range in resumed download")
                    else:
                        offset = (
                            0  # Server ignored Range: safely restart, never append a full file.
                        )
                    with partial.open("ab" if offset else "wb") as stream:
                        count = offset
                        while block := response.read(1024 * 1024):
                            count += len(block)
                            if count > asset["size"]:
                                raise ValueError("Download exceeds declared source size")
                            stream.write(block)
            if (
                partial.stat().st_size != asset["size"]
                or _digest(partial, asset["algorithm"]) != asset["digest"]
            ):
                raise ValueError(
                    f"Download fails size/checksum: {asset['path']}; remove invalid .part to retry"
                )
            partial.replace(target)
            status = "downloaded"
        results.append(
            {
                "path": asset["path"],
                "status": status,
                "sha256": _digest(target, "sha256"),
                "size": asset["size"],
            }
        )
    report = {
        "dataset_id": manifest["dataset_id"],
        "manifest_sha256": _digest(Path(manifest_path), "sha256"),
        "scope": manifest.get("scope", "unspecified"),
        "verified_bytes": total,
        "files": results,
    }
    write_json(root / "acquisition-report.json", report)
    return report


def audit_cohort(cohort_path: str | Path) -> dict:
    """Audit an explicitly mapped cohort; unknown outcomes remain missing, never zero.

    This normalized interchange contract is not a guess at the publisher's table schema.
    Source-specific mapping must be reviewed after the actual tables are obtained.
    """
    from neurocore.io import import_connectome

    cohort = read_json(cohort_path)
    if cohort.get("schema_version") != 1 or not cohort.get("dataset_id"):
        raise ValueError("Expected a version 1 cohort with dataset_id")
    endpoint = cohort.get("endpoint")
    if not isinstance(endpoint, dict) or not endpoint.get("definition"):
        raise ValueError("Cohort requires an explicit outcome endpoint definition")
    followup = endpoint.get("followup_months")
    if type(followup) is not int or followup <= 0:
        raise ValueError("Endpoint followup_months must be a positive integer")
    if not isinstance(cohort.get("subjects"), list):
        raise ValueError("Cohort subjects must be an array")
    base = Path(cohort_path).resolve().parent
    seen, rows = set(), []
    for subject in cohort["subjects"]:
        identifier = subject.get("subject_id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
            raise ValueError("Cohort subject IDs must be nonempty and unique")
        seen.add(identifier)
        reasons = []
        group = subject.get("group")
        if group not in ("surgical_patient", "healthy_control", "unknown"):
            raise ValueError("Group must be surgical_patient, healthy_control, or unknown")
        if group != "surgical_patient":
            reasons.append("not_confirmed_surgical_patient")
        outcome = subject.get("outcome")
        if outcome is None:
            reasons.append("missing_outcome")
        elif type(outcome) is not int or outcome not in (0, 1):
            raise ValueError("Outcome must be null or an explicitly mapped integer 0/1")
        if subject.get("followup_months") != followup:
            reasons.append("followup_does_not_match_endpoint")
        source_refs = subject.get("source_refs")
        if (
            not isinstance(source_refs, list)
            or not source_refs
            or not all(isinstance(ref, str) and ref.strip() for ref in source_refs)
        ):
            reasons.append("missing_source_provenance")
        digest = None
        if not subject.get("connectome"):
            reasons.append("missing_connectome")
        else:
            path = base / _relative_path(subject["connectome"])
            if not path.resolve().is_relative_to(base):
                raise ValueError("Connectome path escapes cohort directory")
            try:
                connectome = import_connectome(path)
                digest = _digest(path, "sha256")
                if connectome["patient_id"] != identifier:
                    reasons.append("patient_id_mismatch")
                if connectome["dataset_id"] != cohort["dataset_id"]:
                    reasons.append("dataset_id_mismatch")
                if connectome["synthetic"]:
                    reasons.append("synthetic_connectome")
                if not connectome["actual_resection"]:
                    reasons.append("missing_resection")
                if not any(r["fraction_removed"] > 0 for r in connectome["actual_resection"]):
                    reasons.append("no_positive_resection_fraction")
                if subject.get("atlas_alignment_reviewed") is not True:
                    reasons.append("atlas_alignment_not_reviewed")
            except ValueError as error:
                reasons.append(f"invalid_connectome: {error}")
        rows.append(
            {
                "subject_id": identifier,
                "group": group,
                "outcome": outcome,
                "eligible_for_retrospective_analysis": not reasons,
                "exclusion_reasons": reasons,
                "connectome_sha256": digest,
            }
        )
    eligible = [row for row in rows if row["eligible_for_retrospective_analysis"]]
    return {
        "schema_version": 1,
        "dataset_id": cohort["dataset_id"],
        "endpoint": endpoint,
        "cohort_sha256": _digest(Path(cohort_path), "sha256"),
        "subject_count": len(rows),
        "eligible_count": len(eligible),
        "class_counts": dict(Counter(str(row["outcome"]) for row in eligible)),
        "exclusion_counts": dict(
            Counter(reason for row in rows for reason in row["exclusion_reasons"])
        ),
        "subjects": rows,
        "limitations": [
            "Eligibility checks do not validate scientific accuracy of source mapping.",
            "Clinical covariates and model-specific requirements need separate validation.",
            "Postoperative resection definitions support retrospective analysis, not prospective validation.",
        ],
    }
