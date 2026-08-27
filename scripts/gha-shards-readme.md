# Unit tests splitting strategy

Unit tests run in parallel across a GitHub Actions matrix. The work is divided by
**measured test duration** using [pytest-split], not by hand-listing directories.

## Configuration

`.github/workflows/unit-test-suites.json` defines two suites:

```json
{
    "lms": { "settings": "lms.envs.test", "paths": ["lms/", "openedx/", ...], "splits": 7 },
    "cms": { "settings": "cms.envs.test", "paths": ["cms/", ...],             "splits": 3 }
}
```

Two suites exist because their tests need different Django settings and so cannot
share a process. `splits` is how many runners that suite is divided across, set
roughly in proportion to its measured work.

## Adding a new Django app

Nothing to do. The `lms` suite tests the repository roots (`lms/`, `openedx/`,
`common/djangoapps/`, `xmodule/`), so a new app under any of them is picked up
automatically.

The `cms` suite is different: it lists `cms/` plus the shared modules that are
*also* exercised under Studio settings. That is a deliberate subset rather than a
mirror of the lms roots, so adding a shared module there is a conscious choice.
See https://github.com/openedx/openedx-platform/issues/38355.

## Timing data

`.test_durations` maps each test to its measured duration and is what makes the
split even. Tests missing from it are assumed to be of average length, so a stale
file degrades balance but never correctness — no test is skipped or duplicated.

Regenerate it from the `pytest-report-*` artifacts that master runs already
upload, then commit the result:

```bash
python scripts/build_test_durations.py path/to/downloaded/artifacts .test_durations
```

Worth doing after a large change in the shape of the suite; not needed routinely.

[pytest-split]: https://github.com/jerry-git/pytest-split
