"""
Emit the settings module, test paths, or split count for a unit-test suite.

Replaces unit_test_shards_parser.py. Work is no longer divided by hand-listing
directories per shard; pytest-split divides it by measured test duration, so a
suite only needs to say which settings it runs under and which paths it covers.
"""
import argparse
import json
import sys

SUITES_JSON = '.github/workflows/unit-test-suites.json'


def get_suites():
    with open(SUITES_JSON) as suites_file:
        return json.load(suites_file)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-name", required=True)
    parser.add_argument("--output", choices=["paths", "settings", "splits"], default="paths")
    args = parser.parse_args()

    suites = get_suites()
    if args.suite_name not in suites:
        print(f"Unknown suite {args.suite_name!r}; expected one of {sorted(suites)}", file=sys.stderr)
        sys.exit(1)

    suite = suites[args.suite_name]
    if args.output == "paths":
        print(' '.join(suite['paths']))
    elif args.output == "settings":
        print(suite['settings'])
    else:
        print(suite['splits'])


if __name__ == "__main__":
    main()
