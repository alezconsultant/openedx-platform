"""
Bump the pinned version of a single package, in whichever file actually pins it.

Used by the "Upgrade one Python dependency" workflow (previously sed-patched
requirements/constraints.txt directly; constraints now live in pyproject.toml and
requirements/team_constraints.txt, so this edits whichever of those actually has
the package instead). Checks requirements/team_constraints.txt first -- a package
pinned there is team-governed and this is the file that should be edited (and the
PR that results should draw that team's review) -- and falls back to
[tool.edx_lint].uv_constraints otherwise. Reads PACKAGE and NEW_VERSION from the
environment so the caller doesn't need to worry about shell-quoting either one.
"""
import os
import re

import tomlkit

TEAM_CONSTRAINTS_PATH = "requirements/team_constraints.txt"
PYPROJECT_PATH = "pyproject.toml"


def normalized_name(spec):
    return re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].lower().replace("_", "-")


def bump_team_constraints(target, new_version):
    with open(TEAM_CONSTRAINTS_PATH, encoding="utf-8") as f:
        lines = f.readlines()

    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "==" in stripped:
            if normalized_name(stripped) == target:
                lines[i] = re.sub(r"==[^\s]+", f"=={new_version}", line)
                found = True
                break

    if found:
        with open(TEAM_CONSTRAINTS_PATH, "w", encoding="utf-8") as f:
            f.writelines(lines)
    return found


def bump_edx_lint_uv_constraints(target, new_version):
    doc = tomlkit.parse(open(PYPROJECT_PATH, encoding="utf-8").read())
    constraints = doc["tool"]["edx_lint"]["uv_constraints"]
    found = False
    for i, spec in enumerate(constraints):
        if normalized_name(str(spec)) == target and "==" in str(spec):
            constraints[i] = re.sub(r"==[^,]+", f"=={new_version}", str(spec))
            found = True
    if found:
        open(PYPROJECT_PATH, "w", encoding="utf-8").write(tomlkit.dumps(doc))
    return found


def main():
    package = os.environ["PACKAGE"]
    new_version = os.environ["NEW_VERSION"]
    target = normalized_name(package)

    if not bump_team_constraints(target, new_version):
        bump_edx_lint_uv_constraints(target, new_version)


if __name__ == "__main__":
    main()
