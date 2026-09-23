# Validation record

The local suite was run against real MCP stdio subprocesses and LangGraph, using
Python 3.12.14, MCP 1.30.0, and LangGraph 1.2.12.

| Check | Result |
| --- | --- |
| Core policy, transport, workflow, and adapter tests | 40 passed |
| Ruff lint and formatting | Passed |
| Actual analyst, finance, support, and denied-access demos | Passed; output in `demo-output.md` |
| Installed local dependencies (`pip check`) | Passed |
| Optional MLflow serving tests | Skipped; SDK installation incomplete |
| Live Databricks requests, resource grants, Search, and Genie | Not run; no workspace credentials |
| Docker build and Python 3.13 | Not run locally; CI configuration is included |

## Optional dependency installation

The Unity Catalog SDK's upper bound on `typing-extensions` conflicts with the newest
AnyIO release. The `databricks` extra constrains a compatible combination to avoid
unbounded dependency backtracking.

The resulting optional dependency installation was then stopped by pip's package
checksum verification, including on a fresh download attempt. Hash checking was not
disabled. This is an installation limitation in the build environment, not evidence
that the optional adapter works in a deployed workspace.

The MCP and model adapter interfaces were checked against official documentation and
downloaded SDK source. Their routing and allowlist logic passed controlled-response
tests. Complete a clean optional install, run `python -m pytest -q` (including the
serving tests), and execute the live workspace checks before claiming cloud integration.

`requirements-dev.lock.txt` records the tested local dependency set. It does not lock
the optional cloud stack and should not be used as cloud-install constraints.
