"""Fail-closed patient, scan, record and feature checks before model fitting."""

from __future__ import annotations

from collections.abc import Sequence

from neurocore.features import FEATURE_SETS
from neurocore.provenance import content_hash


def validate_feature_names(names: Sequence[str]) -> None:
    allowed = set(FEATURE_SETS["C"])
    unknown = sorted(set(names) - allowed)
    if unknown:
        raise ValueError(
            f"DATA_LEAKAGE_DETECTED: unapproved or outcome-derived features: {unknown}"
        )
    if len(names) != len(set(names)):
        raise ValueError("DATA_LEAKAGE_DETECTED: duplicate feature names")


def assert_disjoint_patients(train_ids, validation_ids, test_ids=()) -> None:
    train, validation, test = set(train_ids), set(validation_ids), set(test_ids)
    if train & validation or train & test or validation & test:
        raise ValueError("DATA_LEAKAGE_DETECTED: patient groups overlap across splits")


def validate_records(records: Sequence[dict]) -> None:
    seen_records: set[str] = set()
    seen_features: set[str] = set()
    scan_owner: dict[str, str] = {}
    patient_targets: dict[str, int] = {}
    if not records:
        raise ValueError("Training records must not be empty")
    for record in records:
        for key in ("record_id", "scan_id", "patient_id"):
            if not isinstance(record.get(key), str) or not record[key]:
                raise ValueError(f"Training record {key} must be a nonempty string")
        if record["record_id"] in seen_records:
            raise ValueError("DATA_LEAKAGE_DETECTED: duplicate derived record")
        seen_records.add(record["record_id"])
        scan_id, patient_id = record["scan_id"], record["patient_id"]
        if scan_id in scan_owner and scan_owner[scan_id] != patient_id:
            raise ValueError("DATA_LEAKAGE_DETECTED: shared scan assigned to distinct patients")
        scan_owner[scan_id] = patient_id
        features = record.get("features")
        if not isinstance(features, dict) or not features:
            raise ValueError("Training features must be a nonempty mapping")
        validate_feature_names(list(features))
        fingerprint = content_hash(features)
        if fingerprint in seen_features:
            raise ValueError("DATA_LEAKAGE_DETECTED: duplicate feature row")
        seen_features.add(fingerprint)
        target = record.get("target")
        if isinstance(target, bool) or not isinstance(target, int) or target not in (0, 1):
            raise ValueError("Target must be binary integer 0 or 1")
        if patient_id in patient_targets and patient_targets[patient_id] != target:
            raise ValueError("DATA_LEAKAGE_DETECTED: contradictory patient outcomes")
        patient_targets[patient_id] = target


def validate_split_records(train_records: Sequence[dict], test_records: Sequence[dict]) -> None:
    assert_disjoint_patients(
        [r["patient_id"] for r in train_records], [r["patient_id"] for r in test_records]
    )
    for key in ("scan_id", "record_id"):
        if {record[key] for record in train_records} & {record[key] for record in test_records}:
            raise ValueError(f"DATA_LEAKAGE_DETECTED: shared {key} across splits")
