"""Run the research engine independently of the web/API applications."""

from __future__ import annotations

import argparse
import json
import sys

from neurocore.demo import get_connectome, list_atlases, list_patients
from neurocore.io import export_connectome, import_connectome, read_json, write_json
from neurocore.simulation import simulate


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="neuroresect", description="NeuroResect research engine — synthetic demonstration, not clinical advice")
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
    simulation.add_argument("--regions", help="JSON file containing region_id/fraction_removed array; default is actual_resection")
    simulation.add_argument("--method", choices=["weighted", "binary"], default="weighted")
    simulation.add_argument("--threshold", type=float, default=0.0)
    simulation.add_argument("--output")
    dataset = commands.add_parser("import", help="Validate JSON or CSV with a metadata sidecar")
    dataset.add_argument("path")
    dataset.add_argument("--metadata")
    dataset.add_argument("--output", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "patients":
            result = list_patients()
        elif args.command == "atlases":
            result = list_atlases()
        elif args.command == "inspect":
            result = get_connectome(args.patient_id, args.atlas)
        elif args.command == "import":
            result = import_connectome(args.path, args.metadata)
            export_connectome(result, args.output)
            result = {"status": "validated", "output": args.output, "regions": len(result["nodes"])}
        else:
            connectome = import_connectome(args.input) if args.input else get_connectome(args.patient, args.atlas)
            regions = read_json(args.regions) if args.regions else connectome["actual_resection"]
            result = simulate(connectome, regions, args.method, args.threshold)
        if getattr(args, "output", None) and args.command != "import":
            write_json(args.output, result)
        else:
            print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except ValueError as error:
        print(f"Research input error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
