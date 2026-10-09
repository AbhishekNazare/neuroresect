"""Inspect the released IDEAS II nested network archives without guessing atlas labels."""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import stat
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

import numpy as np

from neurocore.io import read_json, write_json
from neurocore.validation import validate_matrix

MEASURES = {"Count", "CountScaled", "MeanFA", "MeanMD", "MeanLength"}
STRENGTH_MEASURES = {"Count", "CountScaled"}
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_NESTED_BYTES = 8 * 1024**3
MAX_EXPANDED_BYTES = 128 * 1024**3
MEMBER_PATTERN = re.compile(
    r"(?P<method>probabilistic|deterministic)_tractography/"
    r"(?P<atlas>[^/]+)/(?P<subject>sub-[A-Za-z0-9]+)/(?P<session>ses-[A-Za-z0-9]+)/dwi/"
    r"(?P<file_subject>sub-[A-Za-z0-9]+)_(?P<file_session>ses-[A-Za-z0-9]+)_"
    r"(?P<file_method>Probabilistic|Deterministic)-Tractography_"
    r"(?P<file_atlas>[^/]+)_(?P<measure>CountScaled|Count|MeanFA|MeanMD|MeanLength)\.csv"
)


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def checked_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if len(members) > 100_000 or sum(member.file_size for member in members) > MAX_EXPANDED_BYTES:
        raise ValueError("Archive exceeds inventory size limits")
    seen = set()
    for member in members:
        name = member.filename
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or stat.S_ISLNK(member.external_attr >> 16)
            or member.flag_bits & 1
        ):
            raise ValueError(f"Unsafe or encrypted ZIP member: {name}")
        if name in seen:
            raise ValueError(f"Duplicate ZIP member: {name}")
        seen.add(name)
    return members


def prepare_network_archives(source: str | Path, cache: str | Path) -> dict:
    """Extract only the two named nested ZIPs, with CRC verification and hashed reuse."""
    source, cache = Path(source), Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    source_hash = sha256(source)
    record_path = cache / "network-archives.json"
    previous = read_json(record_path) if record_path.exists() else {}
    children = []
    with zipfile.ZipFile(source) as outer:
        checked_members(outer)
        for method in ("probabilistic", "deterministic"):
            member = outer.getinfo(f"networks/{method}_tractography.zip")
            if member.file_size > MAX_NESTED_BYTES:
                raise ValueError("Nested archive exceeds extraction budget")
            target = cache / f"{method}_tractography.zip"
            partial = target.with_suffix(".zip.part")
            if target.is_symlink() or partial.is_symlink():
                raise ValueError("Archive cache files cannot be symlinks")
            old: dict = next(
                (item for item in previous.get("archives", []) if item["method"] == method), {}
            )
            reusable = (
                previous.get("source_sha256") == source_hash
                and target.is_file()
                and target.stat().st_size == member.file_size
                and sha256(target) == old.get("sha256")
            )
            if not reusable:
                if shutil.disk_usage(cache).free < member.file_size:
                    raise ValueError("Insufficient space for nested archive")
                # ZipExtFile validates CRC on reaching EOF; partial never replaces a valid file.
                with outer.open(member) as incoming, partial.open("wb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, length=8 * 1024 * 1024)
                if partial.stat().st_size != member.file_size:
                    raise ValueError("Nested archive size mismatch")
                with zipfile.ZipFile(partial) as nested:
                    checked_members(nested)
                partial.replace(target)
            children.append(
                {
                    "method": method,
                    "path": target.name,
                    "size": member.file_size,
                    "sha256": sha256(target),
                    "outer_crc32": f"{member.CRC:08x}",
                }
            )
    report = {
        "source_name": source.name,
        "source_size": source.stat().st_size,
        "source_sha256": source_hash,
        "archives": children,
        "integrity": "Outer ZIP CRC verified for extracted archives; SHA-256 computed locally.",
    }
    write_json(record_path, report)
    return report


def parse_matrix_member(name: str) -> dict | None:
    match = MEMBER_PATTERN.fullmatch(name)
    if match is None:
        return None
    row = match.groupdict()
    if row["subject"] != row["file_subject"] or row["session"] != row["file_session"]:
        raise ValueError(f"Inconsistent subject/session in matrix path: {name}")
    if row["method"] != row["file_method"].lower():
        raise ValueError(f"Inconsistent tractography method: {name}")
    # The directory's Lausanne-125 corresponds to filename's 125-Lausanne.
    atlas_match = re.fullmatch(r"Lausanne-(\d+)(-Dilated)?", row["atlas"])
    if atlas_match:
        expected = f"{atlas_match[1]}-Lausanne{atlas_match[2] or ''}"
        if row["file_atlas"] != expected:
            raise ValueError(f"Inconsistent atlas identifiers: {name}")
    return {
        "member": name,
        "subject_id": row["subject"],
        "session_id": row["session"],
        "tractography": row["method"],
        "atlas": row["atlas"],
        "measure": row["measure"],
    }


def index_network_archive(path: str | Path) -> dict:
    rows, unrecognized = [], []
    with zipfile.ZipFile(path) as archive:
        for member in checked_members(archive):
            if (
                member.is_dir()
                or member.filename.startswith("__MACOSX/")
                or Path(member.filename).name == ".DS_Store"
            ):
                continue
            row = parse_matrix_member(member.filename)
            if row is None:
                unrecognized.append(member.filename)
                continue
            rows.append({**row, "bytes": member.file_size, "crc32": f"{member.CRC:08x}"})
    observed = {
        (row["subject_id"], row["session_id"], row["atlas"], row["measure"]) for row in rows
    }
    if len(observed) != len(rows):
        raise ValueError("Duplicate subject/session/atlas/measure combinations in archive")
    cases = sorted({(row["subject_id"], row["session_id"]) for row in rows})
    atlases = sorted({row["atlas"] for row in rows})
    missing = [
        {"subject_id": subject, "session_id": session, "atlas": atlas, "measure": measure}
        for subject, session in cases
        for atlas in atlases
        for measure in sorted(MEASURES)
        if (subject, session, atlas, measure) not in observed
    ]
    return {
        "schema_version": 1,
        "archive_sha256": sha256(Path(path)),
        "missing_combination_count": len(missing),
        "missing_combinations": missing,
        "matrix_count": len(rows),
        "subject_count": len({row["subject_id"] for row in rows}),
        "atlas_counts": dict(Counter(row["atlas"] for row in rows)),
        "measure_counts": dict(Counter(row["measure"] for row in rows)),
        "unrecognized_members": unrecognized,
        "matrices": rows,
        "limitations": [
            "Inventory does not validate every numeric matrix or its inner CRC.",
            "Subject identifiers do not establish patient/control status.",
            "Atlas names do not establish region ordering or anatomical coordinates.",
        ],
    }


def read_network_matrix(path: str | Path, member_name: str) -> dict:
    row = parse_matrix_member(member_name)
    if row is None:
        raise ValueError("Unrecognized IDEAS network matrix path")
    with zipfile.ZipFile(path) as archive:
        checked_members(archive)
        member = archive.getinfo(member_name)
        if member.file_size > MAX_MEMBER_BYTES:
            raise ValueError("Matrix exceeds input byte budget")
        data = archive.read(member)  # verifies the inner member CRC
    matrix = validate_matrix(np.loadtxt(io.BytesIO(data), delimiter=","))
    return {
        "schema_version": 1,
        "dataset_id": "ideas-ii-networks-68572654",
        **row,
        "synthetic": False,
        "source_csv_sha256": hashlib.sha256(data).hexdigest(),
        "matrix": matrix.tolist(),
        "region_count": len(matrix),
        "strength_weight_candidate": row["measure"] in STRENGTH_MEASURES,
        "anatomical_mapping_verified": False,
        "limitations": [
            "Source matrix only: not a registered application connectome.",
            "Region labels, coordinates, resection alignment and outcomes still require explicit mapping.",
            "MeanMD and MeanLength must not be interpreted as connection-strength weights.",
        ],
    }


def audit_network_matrices(path: str | Path, atlas: str, measure: str = "Count") -> dict:
    """Check every selected matrix numerically without assigning clinical eligibility."""
    if measure not in MEASURES:
        raise ValueError("Unknown connectivity measure")
    rows = []
    with zipfile.ZipFile(path) as archive:
        for member in checked_members(archive):
            if member.filename.startswith("__MACOSX/"):
                continue
            row = parse_matrix_member(member.filename)
            if row is None or row["atlas"] != atlas or row["measure"] != measure:
                continue
            try:
                if member.file_size > MAX_MEMBER_BYTES:
                    raise ValueError("Matrix exceeds input byte budget")
                data = archive.read(member)
                matrix = validate_matrix(np.loadtxt(io.BytesIO(data), delimiter=","))
                edges = int(np.count_nonzero(np.triu(matrix, 1)))
                rows.append(
                    {
                        **row,
                        "valid": True,
                        "region_count": len(matrix),
                        "edge_count": edges,
                        "isolated_regions": int(np.sum(np.count_nonzero(matrix, axis=1) == 0)),
                        "source_csv_sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
            except (ValueError, zipfile.BadZipFile) as error:
                rows.append({**row, "valid": False, "error": str(error)})
    if not rows:
        raise ValueError("No matrices match the requested atlas and measure")
    return {
        "schema_version": 1,
        "archive_sha256": sha256(Path(path)),
        "atlas": atlas,
        "measure": measure,
        "matrix_count": len(rows),
        "valid_count": sum(row["valid"] for row in rows),
        "invalid_count": sum(not row["valid"] for row in rows),
        "region_counts": dict(Counter(str(row["region_count"]) for row in rows if row["valid"])),
        "matrices": rows,
        "anatomical_mapping_verified": False,
        "limitations": [
            "Numeric validity is not clinical eligibility or anatomical validation.",
            "Disconnected or isolated regions are reported, not silently removed.",
        ],
    }
