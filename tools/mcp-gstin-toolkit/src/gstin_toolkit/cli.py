"""Command-line access to the same checks, for use without an MCP client."""

import argparse
import json

from .audit import audit_csv
from .gstin import validate_gstin


def main() -> None:
    parser = argparse.ArgumentParser(prog="gstin-toolkit", description="Validate GSTINs and audit GST CSV feeds.")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate one or more GSTINs")
    v.add_argument("gstins", nargs="+")

    a = sub.add_parser("audit", help="audit a CSV feed")
    a.add_argument("path")
    a.add_argument("--gstin-column")
    a.add_argument("--state-column")
    a.add_argument("--country-column")
    a.add_argument("--output", help="write the CSV back out with audit columns added")
    a.add_argument("--max-issues", type=int, default=50)

    args = parser.parse_args()
    if args.command == "validate":
        result = [validate_gstin(g).to_dict() for g in args.gstins]
    else:
        result = audit_csv(
            args.path, args.gstin_column, args.state_column, args.country_column, args.output, args.max_issues
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
