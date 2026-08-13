"""
Regenerate uv.lock for every uv sub-project, and the generated .txt
compatibility exports for external tooling (e.g. Tutor's Dockerfile) that
still does `pip install -r requirements/edx/<name>.txt` directly instead of
using uv.

Run by `make compile-requirements`, after the root project's own
`edx_lint write_uv_constraints` / `uv lock` steps. Any argument passed to this script (e.g. `--upgrade`,
`--upgrade-package foo`) is forwarded to every sub-project's `uv lock` call,
mirroring the root project's own `UV_LOCK_OPTS`.

TODO: Remove these exports (for the root project and every sub-project below)
once external consumers (Tutor, Devstack, etc.) have migrated to `uv sync`.
"""
import subprocess
import sys

UV_LOCK_OPTS = sys.argv[1:]

# Root project: each entry is (output path, `uv export` args, doc line).
ROOT_EXPORTS = [
    (
        "requirements/edx/base.txt",
        ["--no-default-groups", "--group", "bundled"],
        "Compatibility export of [project.dependencies] plus the 'bundled' group\n"
        "# (optional third-party add-ons installed by default) for tools that still\n"
        "# 'pip install -r requirements/edx/base.txt' directly instead of using uv.\n"
        "# Source of truth: [project.dependencies] / [dependency-groups].bundled in pyproject.toml / uv.lock.",
    ),
    (
        "requirements/edx/assets.txt",
        ["--only-group", "assets"],
        "Compatibility export of the 'assets' dependency-group for tools that still\n"
        "# 'pip install -r requirements/edx/assets.txt' directly instead of using uv.\n"
        "# Source of truth: [dependency-groups].assets in pyproject.toml / uv.lock.",
    ),
    (
        "requirements/edx/development.txt",
        ["--group", "default"],
        "Compatibility export of the 'default' dependency-group for tools that still\n"
        "# 'pip install -r requirements/edx/development.txt' directly instead of using uv.\n"
        "# Source of truth: [dependency-groups].default in pyproject.toml / uv.lock.",
    ),
]

# Sub-projects with their own pyproject.toml + uv.lock, independent of the
# root project's dependency graph. Each entry is (directory, exports), where
# exports is a list of (output path relative to the sub-project directory,
# extra `uv export` args, doc line).
SUBPROJECTS = [
    (
        "requirements/edx-sandbox",
        [(
            "base.txt", [],
            "Compatibility export for anyone still 'pip install -r requirements/edx-sandbox/base.txt'\n"
            "# directly instead of using uv. Source of truth: requirements/edx-sandbox/pyproject.toml / uv.lock.",
        )],
    ),
    (
        "scripts/xblock",
        [(
            "requirements.txt", [],
            "Compatibility export for anyone still 'pip install -r scripts/xblock/requirements.txt'\n"
            "# directly instead of using uv. Source of truth: scripts/xblock/pyproject.toml / uv.lock.",
        )],
    ),
    ("scripts/semgrep", []),
    (
        "scripts/user_retirement",
        [
            (
                "requirements/base.txt", [],
                "Compatibility export for anyone still 'pip install -r scripts/user_retirement/requirements/base.txt'\n"
                "# directly instead of using uv. Source of truth: scripts/user_retirement/pyproject.toml / uv.lock.",
            ),
            (
                "requirements/testing.txt", ["--group", "test"],
                "Compatibility export for anyone still 'pip install -r scripts/user_retirement/requirements/testing.txt'\n"
                "# directly instead of using uv. Source of truth: scripts/user_retirement/pyproject.toml (test group) / uv.lock.",
            ),
        ],
    ),
    (
        "scripts/structures_pruning",
        [
            (
                "requirements/base.txt", [],
                "Compatibility export for anyone still 'pip install -r scripts/structures_pruning/requirements/base.txt'\n"
                "# directly instead of using uv. Source of truth: scripts/structures_pruning/pyproject.toml / uv.lock.",
            ),
            (
                "requirements/testing.txt", ["--group", "test"],
                "Compatibility export for anyone still 'pip install -r scripts/structures_pruning/requirements/testing.txt'\n"
                "# directly instead of using uv. Source of truth: scripts/structures_pruning/pyproject.toml (test group) / uv.lock.",
            ),
        ],
    ),
]


def write_export(output_path, cwd, export_args, doc_line):
    header = f"# GENERATED FILE, DO NOT EDIT DIRECTLY.\n# {doc_line}\n"
    exported = subprocess.run(
        ["uv", "export", "--frozen", "--no-hashes", *export_args, "--no-emit-project"],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout
    with open(f"{cwd}/{output_path}" if cwd else output_path, "w", encoding="utf-8") as f:
        f.write(header + exported)


def main():
    for output_path, export_args, doc_line in ROOT_EXPORTS:
        write_export(output_path, cwd=None, export_args=export_args, doc_line=doc_line)

    for directory, exports in SUBPROJECTS:
        print(f"\n== {directory} " + "=" * (37 - len(directory)), flush=True)
        subprocess.run(
            ["uv", "run", "--no-project", "--with", "edx-lint", "edx_lint", "write_uv_constraints", "pyproject.toml"],
            cwd=directory, check=True,
        )
        subprocess.run(["uv", "lock", *UV_LOCK_OPTS], cwd=directory, check=True)
        for output_path, export_args, doc_line in exports:
            write_export(output_path, cwd=directory, export_args=export_args, doc_line=doc_line)


if __name__ == "__main__":
    main()
