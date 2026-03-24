# HISTORY

Agent-maintained log of significant changes. Each entry records what was done and who did it.

## 2026-03-24 — v2 extraction migration [claude]

**passport-core 0.2.0**
- Added `extraction/` subpackage: extractor, prompt, models, normalize, validate, confidence
- Added `mrz/` subpackage: TD3 parser, check digits, line building
- Deprecated v1 modules (`workflow.py`, `llm.py`, `models.py`) with `DeprecationWarning`
- Removed `benchmark.py` and its tests
- Removed dead `passport-benchmark` script entry from pyproject.toml

**passport-benchmark 0.2.0**
- Removed experiment code (`extractor_v2.py`, `prompt_v2.py`, `mrz.py`, `run_v1_extractor.py`)
- Updated imports to use `passport_core.extraction` and `passport_core.mrz`
- Updated README and added AGENTS.md

**Root**
- Added extraction pipeline, code quality, and pre-commit checklist rules to AGENTS.md
- Added AGENTS.md to both packages

**Benchmark results**
- v1 workflow: 94.9% accuracy
- v2 extraction: 98.1% accuracy (+3.2pp)
- Model: `google/gemini-3.1-flash-lite-preview`
