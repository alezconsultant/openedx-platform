"""
Bump the pinned version of a single package in [tool.edx_lint].uv_constraints.

Used by the "Upgrade one Python dependency" workflow (previously sed-patched
requirements/constraints.txt directly; constraints now live in pyproject.toml,
so this edits that TOML array instead). Reads PACKAGE and NEW_VERSION from the
environment so the caller doesn't need to worry about shell-quoting either one.
"""
import os
import re

import tomlkit


def normalized_name(spec):
    return re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].lower().replace("_", "-")


def main():
    package = os.environ["PACKAGE"]
    new_version = os.environ["NEW_VERSION"]

    path = "pyproject.toml"
    doc = tomlkit.parse(open(path, encoding="utf-8").read())
    constraints = doc["tool"]["edx_lint"]["uv_constraints"]
    target = normalized_name(package)
    for i, spec in enumerate(constraints):
        if normalized_name(str(spec)) == target and "==" in str(spec):
            constraints[i] = re.sub(r"==[^,]+", f"=={new_version}", str(spec))
    open(path, "w", encoding="utf-8").write(tomlkit.dumps(doc))


if __name__ == "__main__":
    main()
