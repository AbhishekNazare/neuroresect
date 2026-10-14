import json

import boto3
import pytest
from moto import mock_aws
from neurocore.artifacts import LocalStore, S3Store, checksum, publish, restore, verify


@pytest.fixture(params=["local", "s3"])
def store(request, tmp_path):
    if request.param == "local":
        yield LocalStore(tmp_path / "store")
    else:
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket="research-artifacts")
            yield S3Store("research-artifacts", client=client)


def test_bundle_roundtrip_is_reproducible_and_refuses_overwrite(store, tmp_path):
    source = tmp_path / "experiment"
    source.mkdir()
    (source / "config.json").write_text('{"seed":42}')
    (source / "models.joblib").write_bytes(b"opaque-model-never-executed")
    (source / "plots").mkdir()
    (source / "plots" / "metrics.json").write_text('{"auc":0.46}')
    receipt = publish(source, store)
    assert publish(source, store) == receipt
    assert verify(store, receipt["bundle_id"])["file_count"] == 3
    restored = tmp_path / "restored"
    restore(store, receipt["bundle_id"], restored)
    for path in source.rglob("*"):
        if path.is_file():
            target = restored / path.relative_to(source)
            assert target.read_bytes() == path.read_bytes()
            assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        restore(store, receipt["bundle_id"], restored)
    assert (restored / "models.joblib").read_bytes() == b"opaque-model-never-executed"


def corrupt(store, digest):
    if isinstance(store, LocalStore):
        (store.root / digest).write_bytes(b"corrupted")
    else:
        store.client.put_object(Bucket=store.bucket, Key=store.key(digest), Body=b"corrupted")


def test_changed_existing_objects_are_never_silently_reused(store):
    digest = store.put(b"research")
    corrupt(store, digest)
    with pytest.raises(ValueError, match="checksum"):
        store.get(digest)
    with pytest.raises(ValueError, match="checksum"):
        store.put(b"research")


def test_corrupt_bundle_restore_cleans_only_its_new_destination(store, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a").write_bytes(b"first")
    (source / "b").write_bytes(b"second")
    receipt = publish(source, store)
    corrupt(store, checksum(b"second"))
    destination = tmp_path / "restore"
    with pytest.raises(ValueError, match="checksum"):
        restore(store, receipt["bundle_id"], destination)
    assert not destination.exists()
    assert (source / "b").read_bytes() == b"second"


@pytest.mark.parametrize(
    "path", ["../outside", "/absolute", "a/../../outside", "a\\outside", "a/./b", "a//b"]
)
def test_manifest_paths_cannot_escape_destination(store, tmp_path, path):
    digest = store.put(b"payload")
    bundle = store.put(
        json.dumps(
            {
                "format": "neuroresect-artifact-bundle-v1",
                "files": [{"path": path, "sha256": digest, "bytes": 7}],
            }
        ).encode()
    )
    with pytest.raises(ValueError, match="Unsafe"):
        restore(store, bundle, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_source_symlinks_and_nested_store_are_rejected(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    external = tmp_path / "outside"
    external.write_text("outside")
    (source / "link").symlink_to(external)
    with pytest.raises(ValueError, match="symlinks"):
        publish(source, LocalStore(tmp_path / "store"))
    with pytest.raises(ValueError, match="outside the source"):
        publish(source, LocalStore(source / "nested"))


def test_local_store_rejects_object_symlinks(tmp_path):
    store = LocalStore(tmp_path / "store")
    source = tmp_path / "outside"
    source.write_bytes(b"payload")
    (store.root / checksum(b"payload")).symlink_to(source)
    with pytest.raises(ValueError, match="symlink"):
        store.get(checksum(b"payload"))


def test_manifest_file_directory_conflicts_are_rejected(store, tmp_path):
    digest = store.put(b"payload")
    files = [{"path": path, "sha256": digest, "bytes": 7} for path in ["a", "a/b"]]
    bundle = store.put(
        json.dumps({"format": "neuroresect-artifact-bundle-v1", "files": files}).encode()
    )
    with pytest.raises(ValueError, match="conflict"):
        restore(store, bundle, tmp_path / "restore")
