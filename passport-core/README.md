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
├── vision.py            # Face detection, passport validation
├── vision_models.py     # Bounding boxes, validation, and face-detection models
└── io.py                # Image loading
```

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
