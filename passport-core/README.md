# Passport Core

Transport-neutral passport processing engine. Receives image bytes, returns structured extraction results.

## Package Layout

```
passport_core/
├── extraction/          # v2 VLM-based field extraction pipeline
│   ├── extractor.py     # PassportExtractor — main entry point
│   ├── prompt.py        # 7-step extraction prompt
│   ├── models.py        # PassportFields, ExtractionResult, ImageMeta, etc.
│   ├── normalize.py     # Field normalization (dates, MRZ, tokens, text)
│   ├── validate.py      # MRZ ↔ VIZ cross-validation
│   └── confidence.py    # Programmatic confidence from metadata + warnings
├── mrz/                 # MRZ parsing and check digit validation
│   └── parser.py        # TD3 line parsing, building, date conversion
├── config.py            # Settings (PASSPORT_ env prefix)
├── workflow.py          # Legacy v1 workflow (deprecated)
├── llm.py               # Legacy v1 extractor (deprecated)
├── vision.py            # Face detection, passport validation
├── models.py            # Legacy v1 models (deprecated)
└── io.py                # Image loading
```

### Deprecated (v1)

`workflow.py`, `llm.py`, `models.py` — the old flat extraction pipeline. Kept for backward compatibility with `passport-platform`. Will be removed once upstream adapters migrate to `extraction/`.

## Public API

### v2 (extraction subpackage)

```python
from passport_core.extraction import PassportExtractor, ExtractionResult

extractor = PassportExtractor(api_key="...", model="google/gemini-3.1-flash-lite-preview", base_url="https://router.requesty.ai/v1")
result: ExtractionResult = extractor.extract(image_bytes)

result.data          # PassportFields
result.meta          # ImageMeta (orientation, quality, mirrored, skew)
result.confidence    # Confidence (overall + per-field, programmatic)
result.warnings      # MRZ cross-validation warnings
result.reasoning     # VLM reasoning trace
```

### v1 (legacy, deprecated)

```python
from passport_core import PassportWorkflow, Settings

workflow = PassportWorkflow(settings=Settings())
result = workflow.process_bytes(image_bytes, filename="p.jpg", mime_type="image/jpeg")
```

## Installation

```bash
# from the repository root
cp .env.example .env
uv sync --all-packages
```

Use the root `.env.example` and copy it to the repository root `.env`.
Set `PASSPORT_REQUESTY_API_KEY` in the root `.env`.

## Development

```bash
uv run pytest passport-core/tests -q
uv run ruff check passport-core/src passport-core/tests
uv run ruff format passport-core/src passport-core/tests
uv run ty check passport-core/src
```

## Benchmarking

Use `passport-benchmark` (separate package) for evaluation against labeled cases.
