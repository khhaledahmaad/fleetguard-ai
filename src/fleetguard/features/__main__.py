import argparse
from pathlib import Path

from fleetguard.features.hierarchical_dataset import build_feature_dataset, validate_feature_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FleetGuard hierarchical minute summaries, schema 2.0"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--input-dir", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--input-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            report = build_feature_dataset(args.input_dir, args.output_dir, progress=print)
        else:
            report = validate_feature_dataset(args.input_dir)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"FAILED: {error}")
        return 1
    print(f"Validation: {report['status']}")
    print(f"Assets: {report['assets']}")
    for split, count in report["windows_by_split"].items():
        print(f"{split}: {count} wagon minutes")
        if "records_by_split_level" in report:
            for level, records in report["records_by_split_level"][split].items():
                print(f"  {level}: {records} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
