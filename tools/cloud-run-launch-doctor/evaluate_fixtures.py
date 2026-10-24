"""Print synthetic or local labeled Cloud Run log evaluation as JSON."""

import argparse
import json

from evaluation import evaluate_fixture_set, evaluate_labeled_dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        help="Path to a local labels.json manifest for evaluating private log examples.",
    )
    args = parser.parse_args(argv)
    report = (
        evaluate_labeled_dataset(args.dataset)
        if args.dataset
        else evaluate_fixture_set()
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())