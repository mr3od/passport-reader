# AGENTS.md — passport-benchmark

## Purpose

Scoring and evaluation only. Extraction logic lives in `passport-core`.

## Package layout

- `compare.py` — field comparison, Arabic/English normalization, `evaluate_case()`
- `runner.py` — CLI runner, run management, report generation orchestration
- `report.py` — markdown/CSV report output
- `organize.py` — image → case directory organizer
- `draft_unlabeled.py` — generates starter `expected.json` for new cases

## Code quality

- Non-obvious functions must have a Python docstring.
- If a function or module is deprecated, emit `DeprecationWarning` and document the replacement in the docstring.

## Rules

- Imports extraction and MRZ from `passport-core`. No local copies.
- Never modify `cases/labeled/` programmatically — ground truth is human-verified.
- Run results go under `runs/<run-id>/`, never mixed with case directories.
- `manifest.csv` tracks case metadata and must stay in sync with `cases/labeled/`.
