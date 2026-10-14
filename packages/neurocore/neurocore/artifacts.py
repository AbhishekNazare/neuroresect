"""Content-addressed experiment bundles; never deserialize stored model binaries."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from urllib.parse import urlparse

MAX_BYTES = 256 * 1024 * 1024
MAX_FILES = 10000
FORMAT = "neuroresect-artifact-bundle-v1"


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_id(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Artifact IDs must be SHA-256 hex strings")
    return value


def checked(data: bytes, digest: str) -> bytes:
    if len(data) > MAX_BYTES or checksum(data) != object_id(digest):
        raise ValueError("Artifact size limit or checksum verification failed")
    return data


class Store(Protocol):
    def put(self, data: bytes) -> str: ...
    def get(self, digest: str) -> bytes: ...


class LocalStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)

    def get(self, digest: str) -> bytes:
        path = self.root / object_id(digest)
        if path.is_symlink():
            raise ValueError("Artifact object cannot be a symlink")
        with path.open("rb") as stream:
            return checked(stream.read(MAX_BYTES + 1), digest)

    def put(self, data: bytes) -> str:
        digest = checksum(data)
        checked(data, digest)
        descriptor, name = tempfile.mkstemp(prefix=".artifact-", dir=self.root)
        staged = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(staged, self.root / digest)
            except FileExistsError:
                pass
            self.get(digest)  # Detect a corrupted existing object instead of overwriting it.
            descriptor = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            staged.unlink(missing_ok=True)
        return digest


class S3Store:
    def __init__(
        self, bucket: str, prefix: str = "neuroresect", endpoint: str | None = None, client=None
    ):
        import boto3
        from botocore.config import Config

        if not bucket or any(part in {".", ".."} for part in prefix.split("/")):
            raise ValueError("Invalid S3 bucket or prefix")
        self.bucket, self.prefix = bucket, prefix.strip("/")
        self.client = client or boto3.client(
            "s3",
            endpoint_url=endpoint,
            config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 3}),
        )

    def key(self, digest: str) -> str:
        return "/".join(part for part in (self.prefix, "objects", object_id(digest)) if part)

    def get(self, digest: str) -> bytes:
        result = self.client.get_object(Bucket=self.bucket, Key=self.key(digest))
        body = result["Body"]
        try:
            return checked(body.read(MAX_BYTES + 1), digest)
        finally:
            body.close()

    def put(self, data: bytes) -> str:
        from botocore.exceptions import ClientError

        digest = checksum(data)
        checked(data, digest)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=self.key(digest),
                Body=data,
                IfNoneMatch="*",
                ChecksumSHA256=base64.b64encode(bytes.fromhex(digest)).decode(),
            )
        except ClientError as exc:
            if str(exc.response["Error"]["Code"]) not in {"PreconditionFailed", "412"}:
                raise
        self.get(digest)
        return digest


def relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("Unsafe artifact path")
    return path


def publish(source: Path, store: Store) -> dict:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Publish requires a regular directory")
    if isinstance(store, LocalStore) and (
        store.root == source.resolve() or source.resolve() in store.root.parents
    ):
        raise ValueError("Artifact store must be outside the source directory")
    files: list[dict[str, Any]] = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Artifact bundles cannot include symlinks")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Artifact bundles contain only regular files")
        name = relative_path(path.relative_to(source).as_posix()).as_posix()
        with path.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or len(files) >= MAX_FILES:
            raise ValueError("Artifact bundle exceeds file size/count limits")
        files.append({"path": name, "sha256": store.put(data), "bytes": len(data)})
    if not files:
        raise ValueError("Artifact directory is empty")
    manifest = {"format": FORMAT, "files": files}
    data = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return {
        "bundle_id": store.put(data),
        "file_count": len(files),
        "total_bytes": sum(row["bytes"] for row in files),
    }


def manifest(store: Store, bundle_id: str) -> dict:
    result = json.loads(store.get(bundle_id))
    if not isinstance(result, dict) or result.get("format") != FORMAT:
        raise ValueError("Unsupported artifact manifest")
    files = result.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("Invalid artifact inventory")
    paths = set()
    for row in files:
        path = relative_path(row["path"])
        object_id(row["sha256"])
        if not isinstance(row["bytes"], int) or not 0 <= row["bytes"] <= MAX_BYTES or path in paths:
            raise ValueError("Invalid artifact size or duplicate path")
        paths.add(path)
    if any(parent in paths for path in paths for parent in path.parents):
        raise ValueError("Artifact paths conflict")
    return result


def verify(store: Store, bundle_id: str) -> dict:
    result = manifest(store, bundle_id)
    for row in result["files"]:
        if len(store.get(row["sha256"])) != row["bytes"]:
            raise ValueError("Artifact size differs from manifest")
    return {"bundle_id": bundle_id, "file_count": len(result["files"]), "verified": True}


def restore(store: Store, bundle_id: str, destination: Path) -> dict:
    result = manifest(store, bundle_id)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        for row in result["files"]:
            data = store.get(row["sha256"])
            if len(data) != row["bytes"]:
                raise ValueError("Artifact size differs from manifest")
            path = destination / row["path"]
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with path.open("xb") as stream:
                os.chmod(path, 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {
        "bundle_id": bundle_id,
        "file_count": len(result["files"]),
        "destination": str(destination),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store", default="data/artifact-store", help="Local directory or s3://bucket/prefix"
    )
    parser.add_argument("--endpoint-url", default=os.getenv("S3_ENDPOINT_URL"))
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("publish")
    save.add_argument("directory", type=Path)
    check = commands.add_parser("verify")
    check.add_argument("bundle_id", type=object_id)
    recover = commands.add_parser("restore")
    recover.add_argument("bundle_id", type=object_id)
    recover.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    parsed = urlparse(args.store)
    store: Store
    if parsed.scheme == "s3":
        if parsed.query or parsed.fragment or parsed.username:
            parser.error("S3 store URLs contain only bucket and prefix")
        store = S3Store(parsed.netloc, parsed.path.strip("/"), args.endpoint_url)
    elif parsed.scheme:
        parser.error("Store must be a local directory or s3:// URL")
    else:
        store = LocalStore(Path(args.store))
    if args.command == "publish":
        result = publish(args.directory, store)
    elif args.command == "verify":
        result = verify(store, args.bundle_id)
    else:
        result = restore(store, args.bundle_id, args.destination)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
