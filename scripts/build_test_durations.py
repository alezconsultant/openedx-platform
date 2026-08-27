"""
Build the per-suite .test_durations files from the pytest --report-log artifacts
that master runs upload.

Usage:
    python scripts/build_test_durations.py <artifact-dir> [output-dir]

Writes .test_durations.lms and .test_durations.cms. One file per suite is
required, not one overall: ~8,000 tests under openedx/, common/ and xmodule/ run
under *both* Django settings and report the same node id each time. Merging them
would double those tests' recorded duration and skew every split that contains
one. The suite a report belongs to is taken from its filename.

Durations for each phase (setup, call, teardown) are summed per test, which is
what pytest-split measures against.
"""
import json
import pathlib
import sys

# A test that manipulates the clock (freezegun and friends) can report a wildly
# out-of-range duration -- one observed pair was +1.79e9s in setup and the exact
# negative in teardown. They cancel out overall but poison that test's total, so
# drop anything outside a plausible range rather than trusting it.
MAX_PLAUSIBLE_SECONDS = 600


def suite_for(report_path):
    """Which suite a pytest-report-*.jsonl belongs to.

    Handles the current pytest-report-<suite>-<group>.jsonl names and the older
    per-shard ones (lms-3, shared-with-cms-1, cms-2). Only the cms suite runs
    under Studio settings, and only its shard names contain "cms".
    """
    return 'cms' if 'cms' in report_path.name else 'lms'


def build(artifact_dir):
    durations = {'lms': {}, 'cms': {}}
    dropped = 0
    for path in pathlib.Path(artifact_dir).rglob('*.jsonl'):
        suite = durations[suite_for(path)]
        with open(path) as report:
            for line in report:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get('$report_type') != 'TestReport':
                    continue
                seconds = entry.get('duration', 0.0)
                if not isinstance(seconds, (int, float)) or not 0 <= seconds <= MAX_PLAUSIBLE_SECONDS:
                    dropped += 1
                    continue
                node_id = entry.get('nodeid')
                if node_id:
                    suite[node_id] = suite.get(node_id, 0.0) + seconds
    return {name: {k: round(v, 3) for k, v in sorted(entries.items())}
            for name, entries in durations.items()}, dropped


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(1)
    output_dir = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else '.')
    by_suite, dropped = build(sys.argv[1])
    if not any(by_suite.values()):
        print(f"No test reports found under {sys.argv[1]!r}", file=sys.stderr)
        sys.exit(1)
    for suite, durations in by_suite.items():
        if not durations:
            print(f"warning: no reports for the {suite} suite", file=sys.stderr)
            continue
        output = output_dir / f'.test_durations.{suite}'
        # One entry per line: a single-line JSON blob of this size is unreviewable.
        with open(output, 'w') as out:
            out.write('{\n')
            out.write(',\n'.join(f'{json.dumps(k)}:{v}' for k, v in durations.items()))
            out.write('\n}\n')
        print(f"{suite}: {len(durations):,} tests, {sum(durations.values())/60:.0f} min -> {output}")
    if dropped:
        print(f"({dropped} implausible durations dropped)")


if __name__ == "__main__":
    main()
