scripts/semgrep: an isolated environment for running semgrep
##############################################################

This directory holds a standalone ``uv``-managed environment
(``pyproject.toml`` + ``uv.lock``) for the `semgrep <https://semgrep.dev/>`_
CLI, used by the ``.github/workflows/semgrep.yml`` CI job to scan ``lms``,
``cms``, ``common``, and ``openedx`` against the rules in
``test_root/semgrep/``.

It's isolated from the main application's dependency graph -- rather than a
``[dependency-groups]`` entry in the root ``pyproject.toml`` -- because
semgrep's own dependency chain (via ``wcmatch``) is incompatible with other
root-project dependencies (e.g. ``openedx-authz``'s ``pycasbin`` pin) when
resolved together in one shared graph. This mirrors why
``requirements/edx-sandbox`` and ``scripts/xblock`` are isolated the same way.

Regenerate ``uv.lock`` by running ``make compile-requirements`` or
``make upgrade`` from the repo root -- see the ``scripts/semgrep`` entry in
the root ``Makefile``'s ``compile-requirements`` target.
