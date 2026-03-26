# AGENTS.md — passport-core

## Boundaries

- No imports from other repo packages.
- No database access, no filesystem state.
- Stateless: image bytes in, structured result out.

## Package structure

- `extraction/` — v2 pipeline. `PassportExtractor.extract()` is the entry point.
- `mrz/` — MRZ parsing, check digits, line building. Self-contained, no LLM dependency.
- `vision.py` + `vision_models.py` — passport validation and face-detection support for the image-processing pipeline.

## Key conventions

- Fields use `GivenNameTokensAr/En` (list of tokens), not concatenated name strings.
- Dates are `DD/MM/YYYY`. Sex is `M`/`F` or null.
- MRZ lines are exactly 44 characters, padded with `<`.
- Confidence is computed programmatically from image metadata + cross-validation warnings — never from LLM self-reported scores.
- Arabic text is extracted as-is from the image. Never back-translate from English.

## Code quality

- Non-obvious functions must have a Python docstring explaining what they do.
- Deprecated modules must emit `DeprecationWarning` at import time and carry a `.. deprecated::` directive in their module docstring pointing to the replacement.
- New extraction work goes in `extraction/` or `mrz/`. Do not recreate the removed v1 API.

## Testing

```bash
uv run pytest passport-core/tests -q
uv run ruff check passport-core/src passport-core/tests
uv run ty check passport-core/src
```

Run commands from the repository root. Local configuration comes from the root `.env`.

Benchmarking lives in `passport-benchmark/`, not here.
