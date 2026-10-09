"""Run the research engine independently of the web/API applications."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from typing import Any

from neurocore.demo import get_connectome, list_atlases, list_patients
from neurocore.io import export_connectome, import_connectome, read_json, write_json
from neurocore.simulation import simulate


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="neuroresect",
        description="NeuroResect research engine — synthetic demonstration, not clinical advice",
    )
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("patients", help="List the synthetic demonstration cohort")
    commands.add_parser("atlases", help="List illustrative atlases")
    inspect = commands.add_parser("inspect", help="Export a synthetic connectome")
    inspect.add_argument("patient_id")
    inspect.add_argument("--atlas", default="demo-64")
    inspect.add_argument("--output")
    simulation = commands.add_parser("simulate", help="Simulate JSON resection fractions")
    source = simulation.add_mutually_exclusive_group(required=True)
    source.add_argument("--patient")
    source.add_argument("--input", help="Validated connectome JSON file")
    simulation.add_argument("--atlas", default="demo-64")
    simulation.add_argument(
        "--regions",
        help="JSON file containing region_id/fraction_removed array; default is actual_resection",
    )
    simulation.add_argument("--method", choices=["weighted", "binary"], default="weighted")
    simulation.add_argument("--threshold", type=float, default=0.0)
    simulation.add_argument("--output")
    dataset = commands.add_parser("import", help="Validate JSON or CSV with a metadata sidecar")
    dataset.add_argument("path")
    dataset.add_argument("--metadata")
    dataset.add_argument("--output", required=True)
    experiment = commands.add_parser("experiment", help="Run a patient-separated A/B/C study")
    experiment.add_argument("config", help="JSON experiment configuration")
    experiment.add_argument("--output", required=True, help="Artifact directory")
    reproduce = commands.add_parser(
        "reproduce", help="Reproduce and compare an exported experiment"
    )
    reproduce.add_argument("artifact")
    reproduce.add_argument("--output", required=True, help="Artifact directory")
    ideas = commands.add_parser("ideas-discover", help="Inventory pinned IDEAS II release metadata")
    ideas.add_argument("--output", required=True)
    ideas.add_argument("--subject", action="append", dest="subjects")
    download = commands.add_parser("dataset-download", help="Download checksum-pinned assets")
    download.add_argument("manifest")
    download.add_argument("--destination", required=True)
    download.add_argument("--max-bytes", type=int, default=100_000_000)
    audit = commands.add_parser(
        "cohort-audit", help="Audit explicitly mapped real-data eligibility"
    )
    audit.add_argument("cohort")
    audit.add_argument("--output", required=True)
    networks = commands.add_parser("ideas-networks", help="Inspect real IDEAS network archives")
    networks.add_argument("archive")
    networks.add_argument("--cache", required=True)
    networks.add_argument("--output", required=True)
    matrix = commands.add_parser(
        "ideas-matrix", help="Validate one source matrix without guessing anatomy"
    )
    matrix.add_argument("archive", help="Extracted probabilistic or deterministic ZIP")
    matrix.add_argument(
        "--member", required=True, help="Exact member path from the network inventory"
    )
    matrix.add_argument("--output", required=True)
    matrix_audit = commands.add_parser(
        "ideas-matrix-audit", help="Audit all matrices for one atlas/measure"
    )
    matrix_audit.add_argument("archive")
    matrix_audit.add_argument("--atlas", required=True)
    matrix_audit.add_argument("--measure", default="Count")
    matrix_audit.add_argument("--output", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result: Any
    try:
        if args.command == "ideas-matrix-audit":
            from neurocore.ideas import audit_network_matrices

            result = audit_network_matrices(args.archive, args.atlas, args.measure)
            write_json(args.output, result)
            print(
                json.dumps(
                    {key: value for key, value in result.items() if key != "matrices"}, indent=2
                )
            )
            return 2 if result["invalid_count"] else 0
        elif args.command in ("ideas-networks", "ideas-matrix"):
            from pathlib import Path

            from neurocore.ideas import (
                index_network_archive,
                prepare_network_archives,
                read_network_matrix,
            )

            if args.command == "ideas-networks":
                acquisition = prepare_network_archives(args.archive, args.cache)
                result = {"acquisition": acquisition, "inventories": {}}
                for archive in acquisition["archives"]:
                    inventory = index_network_archive(Path(args.cache) / archive["path"])
                    write_json(Path(args.output) / f"{archive['method']}-inventory.json", inventory)
                    result["inventories"][archive["method"]] = {
                        key: value
                        for key, value in inventory.items()
                        if key not in ("matrices", "missing_combinations")
                    }
                write_json(Path(args.output) / "summary.json", result)
            else:
                result = read_network_matrix(args.archive, args.member)
                write_json(args.output, result)
                result = {key: value for key, value in result.items() if key != "matrix"}
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0
        elif args.command in ("ideas-discover", "dataset-download", "cohort-audit"):
            from neurocore.datasets import audit_cohort, discover_ideas, download_manifest

            if args.command == "ideas-discover":
                result = discover_ideas(args.output, args.subjects)
            elif args.command == "dataset-download":
                result = download_manifest(args.manifest, args.destination, args.max_bytes)
            else:
                result = audit_cohort(args.cohort)
                write_json(args.output, result)
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0
        elif args.command == "patients":
            result = list_patients()
        elif args.command == "atlases":
            result = list_atlases()
        elif args.command == "inspect":
            result = get_connectome(args.patient_id, args.atlas)
        elif args.command == "import":
            result = import_connectome(args.path, args.metadata)
            export_connectome(result, args.output)
            result = {"status": "validated", "output": args.output, "regions": len(result["nodes"])}
        elif args.command in ("experiment", "reproduce"):
            from neurocore.experiments import reproduce_experiment, run_experiment

            if args.command == "experiment":
                result = run_experiment(read_json(args.config), args.output)
            else:
                result = reproduce_experiment(args.artifact, args.output)
            print(
                json.dumps(
                    {
                        "id": result["id"],
                        "output": args.output,
                        "reproduction": result.get("reproduction"),
                    },
                    indent=2,
                )
            )
            return 2 if result.get("reproduction", {}).get("matches") is False else 0
        else:
            connectome = (
                import_connectome(args.input)
                if args.input
                else get_connectome(args.patient, args.atlas)
            )
            regions = read_json(args.regions) if args.regions else connectome["actual_resection"]
            result = simulate(connectome, regions, args.method, args.threshold)
        if getattr(args, "output", None) and args.command != "import":
            write_json(args.output, result)
        else:
            print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, zipfile.BadZipFile, KeyError) as error:
        print(f"Research input error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
