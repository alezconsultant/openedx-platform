"""
Fail if any test file is not covered by a unit-test suite.

The suites in .github/workflows/unit-test-suites.json enumerate the paths each
one runs. That list is maintained by hand -- it cannot simply be the repository
roots, because a few apps under openedx/ are Studio-only and raise at import
under lms settings -- so it can drift when a new Django app is added.

This replaces the old collect-and-verify job, which compared test *counts*
between the shard list and the roots. Comparing the paths directly says which
directory is missing rather than only that some number disagrees.
"""
import json
import pathlib
import sys

SUITES_JSON = '.github/workflows/unit-test-suites.json'
ROOTS = ('lms', 'cms', 'openedx', 'common/djangoapps', 'xmodule')
TEST_GLOBS = ('test_*.py', 'tests.py', 'tests_*.py', '*_tests.py')
# Mirrors norecursedirs in pyproject.toml, plus trees that hold fixtures rather
# than collectable tests.
SKIP = ('node_modules', '/envs/', '/migrations/', 'test_root', '/.git/', '/features/')


def covered_paths():
    with open(SUITES_JSON) as suites_file:
        suites = json.load(suites_file)
    return tuple({path for suite in suites.values() for path in suite['paths']})


def find_test_files():
    for root in ROOTS:
        for glob in TEST_GLOBS:
            for path in pathlib.Path(root).rglob(glob):
                text = str(path)
                if not any(skip in f'/{text}' for skip in SKIP):
                    yield text


def main():
    prefixes = covered_paths()
    uncovered = sorted({
        str(pathlib.Path(f).parent) for f in find_test_files()
        if not f.startswith(prefixes)
    })
    if uncovered:
        print("::error title=Unit test suites are out of date::"
              "These directories contain tests that no suite in "
              f"{SUITES_JSON} covers, so they never run in CI. Add them to the "
              "lms suite, or to the cms suite if they need Studio settings.")
        for directory in uncovered:
            print(f"  {directory}")
        sys.exit(1)
    print(f"All test files are covered by {len(prefixes)} suite paths.")


if __name__ == "__main__":
    main()
