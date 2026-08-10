"""
Merge requirements/team_constraints.txt into [tool.uv].constraint-dependencies.

Run by `make compile-requirements`, after `edx_lint write_uv_constraints` (which
owns/overwrites that list from edx_lint's global constraints plus this repo's
[tool.edx_lint].uv_constraints) and before `uv lock`. An entry here always
replaces whatever write_uv_constraints produced for the same package -- these
pins are team-governed and must not silently move on a routine `make upgrade`.
"""
import re

import tomlkit

TEAM_CONSTRAINTS_PATH = "requirements/team_constraints.txt"
PYPROJECT_PATH = "pyproject.toml"


def normalized_name(spec):
    return re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].lower().replace("_", "-")


def read_team_constraints():
    constraints = []
    with open(TEAM_CONSTRAINTS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                constraints.append(line)
    return constraints


def main():
    team_constraints = read_team_constraints()

    doc = tomlkit.parse(open(PYPROJECT_PATH, encoding="utf-8").read())
    constraints = doc["tool"]["uv"]["constraint-dependencies"]

    for team_spec in team_constraints:
        target = normalized_name(team_spec)
        for i, existing in enumerate(constraints):
            if normalized_name(str(existing)) == target:
                constraints[i] = team_spec
                break
        else:
            constraints.append(team_spec)

    open(PYPROJECT_PATH, "w", encoding="utf-8").write(tomlkit.dumps(doc))


if __name__ == "__main__":
    main()
