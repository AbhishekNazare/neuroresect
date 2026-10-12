"""Back up the configured Compose PostgreSQL service; restore only to a new database."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

FORMAT = "neuroresect-postgres-backup-v1"


def identifier(value):
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value):
        raise ValueError("Use a lowercase database/user identifier of at most 63 characters")
    return value


def run(arguments, *, stdin=None, stdout=subprocess.PIPE):
    result = subprocess.run(
        ["docker", "compose", *arguments],
        stdin=stdin,
        stdout=stdout,
        stderr=subprocess.PIPE,
        timeout=1200,
    )
    if result.returncode:
        raise RuntimeError(
            "Compose PostgreSQL operation failed; no existing database was replaced. Inspect service health and use the matching application image"
        )
    return result.stdout


def pg(*arguments, **kwargs):
    return run(["exec", "-T", "postgres", *arguments], **kwargs)


def inspect_database(database, finalize=False):
    args = [
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "api",
        "python",
        "-m",
        "neuroresect_api.recovery_admin",
        "--database-name",
        identifier(database),
    ]
    if finalize:
        args.append("--finalize")
    return json.loads(run(args))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def backup(output, database="neuroresect", user="neuroresect"):
    identifier(database)
    identifier(user)
    source = inspect_database(database)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        archive = output / "database.dump"
        with archive.open("xb") as stream:
            os.chmod(archive, 0o600)
            pg(
                "pg_dump",
                "--username",
                user,
                "--dbname",
                database,
                "--format=custom",
                "--no-owner",
                "--no-acl",
                stdout=stream,
            )
            stream.flush()
            os.fsync(stream.fileno())
        with archive.open("rb") as stream:
            pg("pg_restore", "--list", stdin=stream)
        manifest = {
            "format": FORMAT,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "archive_sha256": digest(archive),
            "archive_bytes": archive.stat().st_size,
            "schema_revision": source["schema_revision"],
            "pg_dump_version": pg("pg_dump", "--version").decode().strip(),
            "scope": "Application PostgreSQL database; excludes roles, ACLs, Redis queues and external artifacts",
        }
        path = output / "manifest.json"
        with path.open("x") as stream:
            os.chmod(path, 0o600)
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        for directory in (output, output.parent):
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return manifest
    except BaseException:
        shutil.rmtree(output)
        raise


def verify(bundle):
    manifest = json.loads((bundle / "manifest.json").read_text())
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise ValueError("Unsupported PostgreSQL backup format")
    archive = bundle / "database.dump"
    if (
        archive.stat().st_size != manifest["archive_bytes"]
        or digest(archive) != manifest["archive_sha256"]
    ):
        raise ValueError("Backup checksum or size mismatch")
    with archive.open("rb") as stream:
        pg("pg_restore", "--list", stdin=stream)
    return manifest


def restore(bundle, destination, user="neuroresect"):
    identifier(destination)
    identifier(user)
    manifest = verify(bundle)
    with tempfile.TemporaryFile() as staged:
        with (bundle / "database.dump").open("rb") as stream:
            shutil.copyfileobj(stream, staged)
        staged.seek(0)
        if hashlib.file_digest(staged, "sha256").hexdigest() != manifest["archive_sha256"]:
            raise ValueError("Backup changed during restore")
        staged.seek(0)
        # createdb fails atomically if this name exists. No DROP, --clean or overwrite option.
        pg("createdb", "--username", user, "--template=template0", destination)
        try:
            pg(
                "pg_restore",
                "--username",
                user,
                "--dbname",
                destination,
                "--single-transaction",
                "--no-owner",
                "--no-acl",
                stdin=staged,
            )
            report = inspect_database(destination)
            if report["schema_revision"] != manifest["schema_revision"]:
                raise ValueError("Restored schema revision differs from backup manifest")
            report = inspect_database(destination, finalize=True)
        except Exception as exc:
            raise RuntimeError(
                f"Restore validation failed; new database {destination} is retained for inspection and must not be activated"
            ) from exc
    return {"database": destination, "archive_sha256": manifest["archive_sha256"], **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("backup")
    save.add_argument("--output", type=Path, required=True)
    save.add_argument("--database", default="neuroresect")
    save.add_argument("--user", default="neuroresect")
    check = commands.add_parser("verify")
    check.add_argument("bundle", type=Path)
    recover = commands.add_parser("restore")
    recover.add_argument("bundle", type=Path)
    recover.add_argument("--destination", required=True)
    recover.add_argument("--user", default="neuroresect")
    args = parser.parse_args()
    try:
        if args.command == "backup":
            result = backup(args.output, args.database, args.user)
        elif args.command == "verify":
            result = verify(args.bundle)
        else:
            result = restore(args.bundle, args.destination, args.user)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"PostgreSQL recovery failed: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
