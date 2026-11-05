"""CLI for CI evidence collection and verification."""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.evidence import (
    CheckSpec,
    build_record,
    load_record,
    read_coverage,
    run_checks,
    verify_record,
    write_record,
)


def _parse_check(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("check must be name=command")
    name, command = value.split("=", 1)
    if not name or not command:
        raise argparse.ArgumentTypeError("check must be name=command")
    return name, command


def _record(args: argparse.Namespace) -> int:
    specs = [CheckSpec(name, command, True) for name, command in args.check]
    specs += [CheckSpec(name, command, False) for name, command in args.advisory]
    checks = run_checks(specs, cwd=args.cwd)
    coverage = read_coverage(args.coverage_xml) if args.coverage_xml else None
    record = build_record(
        workflow=args.workflow,
        commit=args.commit,
        checks=checks,
        coverage=coverage,
        min_coverage=args.min_coverage,
    )
    write_record(record, args.out)
    required_failed = any(
        check["required"] and check["status"] != "passed" for check in checks
    )
    print(f"evidence written to {args.out}")
    return 1 if required_failed else 0


def _verify(args: argparse.Namespace) -> int:
    failures: list[str] = []
    for path in args.files:
        try:
            record = load_record(path)
        except (OSError, ValueError) as exc:
            failures.append(f"{path}: {exc}")
            continue
        errors = verify_record(
            record,
            expected_commit=args.commit,
            max_age_hours=args.max_age_hours,
        )
        if errors:
            failures.extend(f"{path}: {error}" for error in errors)
        else:
            print(f"verified {path} ({record.get('workflow')})")
    for failure in failures:
        print(f"ERROR: {failure}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="run checks and write an evidence record")
    record.add_argument("--out", required=True)
    record.add_argument("--workflow", required=True)
    record.add_argument("--commit", required=True)
    record.add_argument("--cwd", default=None)
    record.add_argument("--coverage-xml", default=None)
    record.add_argument("--min-coverage", type=float, default=None)
    record.add_argument("--check", action="append", type=_parse_check, default=[])
    record.add_argument("--advisory", action="append", type=_parse_check, default=[])
    record.set_defaults(func=_record)

    verify = sub.add_parser("verify", help="verify one or more evidence records")
    verify.add_argument("files", nargs="+")
    verify.add_argument("--commit", required=True)
    verify.add_argument("--max-age-hours", type=int, default=24)
    verify.set_defaults(func=_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
