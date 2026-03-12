# Passport Core

`passport-core` is the passport-processing package used for Yemeni travel-agency workflows.

It takes a passport image, validates that the page is really a passport, detects and crops the face, extracts structured fields with an LLM, and stores both the binary artifacts and the unified result record.

Pipeline:

`load -> store original -> validate -> detect face -> crop face -> extract fields -> store result`

## What It Produces

Each processed source returns one `PassportProcessingResult` with:

- `source`: input path or URL
- `trace_id`: per-request identifier
- `passport_image_uri`: stored original image location
- `face_crop_uri`: stored cropped-face location
- `validation`: passport match result and debug counters
- `face`: detected face bounding box
- `data`: extracted `PassportData`
- `error_details`: stage-specific failures without losing the rest of the result

The extractor returns these fields:

- `PassportNumber`
- `CountryCode`
- `MrzLine1`
- `MrzLine2`
- `SurnameAr`
- `GivenNamesAr`
- `SurnameEn`
- `GivenNamesEn`
- `DateOfBirth`
- `PlaceOfBirthAr`
- `PlaceOfBirthEn`
- `Sex`
- `DateOfIssue`
- `DateOfExpiry`
- `ProfessionAr`
- `ProfessionEn`
- `IssuingAuthorityAr`
- `IssuingAuthorityEn`

## Requirements

- Python 3.12+
- OpenCV with SIFT and `FaceDetectorYN` support
- `assets/passport_template_v2.jpg`
- `assets/face_detection_yunet_2023mar.onnx`
- A Requesty API key in `PASSPORT_REQUESTY_API_KEY`

Note: the current `PassportCoreService` always initializes the LLM extractor during startup. In practice that means normal processing requires both the `llm` extra and `PASSPORT_REQUESTY_API_KEY`, even if you only care about validation or face detection.

## Installation

### With `uv`

```bash
cd passport-core
uv venv --python 3.12
source .venv/bin/activate
uv sync --extra llm --extra dev
cp .env.example .env
```

### With `pip`

```bash
cd passport-core
python -m venv .venv
source .venv/bin/activate
pip install -e '.[llm,dev]'
cp .env.example .env
```

Then set at least:

```bash
export PASSPORT_REQUESTY_API_KEY=your_key_here
```

## Configuration

All settings use the `PASSPORT_` prefix and are loaded from environment variables or `.env`.

Common settings:

- `PASSPORT_TEMPLATE_PATH`: masked passport template used by SIFT validation
- `PASSPORT_FACE_MODEL_PATH`: YuNet ONNX model used for face detection
- `PASSPORT_STORAGE_BACKEND`: `local` or `s3`
- `PASSPORT_LOCAL_STORAGE_DIR`: local binary output directory, default `data`
- `PASSPORT_S3_BUCKET`: required when `PASSPORT_STORAGE_BACKEND=s3`
- `PASSPORT_DATA_STORE_BACKEND`: `sqlite`, `json`, or `csv`
- `PASSPORT_DATA_STORE_PATH`: result-store root, default `data`
- `PASSPORT_LLM_MODEL`: default `openai-responses/gpt-5-mini`
- `PASSPORT_REQUESTY_API_KEY`: required for extraction
- `PASSPORT_REQUESTY_BASE_URL`: default `https://router.requesty.ai/v1`
- `PASSPORT_LOG_LEVEL`: default `INFO`
- `PASSPORT_LOG_JSON`: set `true` for JSON logs

Validation and detector thresholds are also configurable; see `.env.example` for the full set.

## Default Storage Layout

With default settings:

- original images are stored under `data/originals/YYYYMMDD/`
- cropped faces are stored under `data/faces/YYYYMMDD/`
- result records are stored in `data/results.sqlite3`

If `PASSPORT_DATA_STORE_BACKEND=json`, results are written to `data/results/*.json`.

If `PASSPORT_DATA_STORE_BACKEND=csv`, results are appended to `data/results.csv`.

## CLI

The package installs two commands:

- `passport-core`
- `passport-benchmark`

### Process one or more files

`simulate-agency` is an alias for `process`.

```bash
passport-core process tests/fixtures/abdullah_passport.jpg \
  tests/fixtures/salem_passport.jpeg \
  --pretty \
  --out-json agency_results.json \
  --csv-output enjaz.csv
```

### Simulate an agency upload batch

```bash
passport-core simulate-agency tests/fixtures/abdullah_passport.jpg \
  tests/fixtures/salem_passport.jpeg \
  --pretty
```

### Process a directory

Supported extensions are `.jpg`, `.jpeg`, `.png`, `.webp`, `.tif`, and `.tiff`.

```bash
passport-core process-dir agency-input \
  --pretty \
  --out-json agency_results.json \
  --csv-output enjaz.csv
```

Include nested folders:

```bash
passport-core process-dir agency-input --recursive --pretty
```

### Crop the detected face only

```bash
passport-core crop-face tests/fixtures/abdullah_passport.jpg --pretty
```

## Python Usage

```python
from passport_core import PassportCoreService, Settings

settings = Settings()
service = PassportCoreService(settings=settings)

try:
    result = service.process_source("tests/fixtures/abdullah_passport.jpg")

    print(result.validation.is_passport)
    print(result.passport_image_uri)
    print(result.face_crop_uri)
    print(result.data.PassportNumber if result.data else None)
    print(result.error_details)
finally:
    service.close()
```

You can also process multiple sources:

```python
results = service.process_sources(
    [
        "tests/fixtures/abdullah_passport.jpg",
        "tests/fixtures/salem_passport.jpeg",
    ]
)
```

Export Enjaz-compatible CSV from in-memory results:

```python
service.export_results_csv(results, "enjaz.csv")
```

Export everything already saved in the configured result store:

```python
service.export_all_csv("all_results.csv")
```

## Input Sources

`ImageLoader` accepts:

- local file paths
- remote `http` and `https` URLs

Remote downloads are limited by `PASSPORT_MAX_DOWNLOAD_BYTES` and reject localhost-style hosts such as `localhost`, `127.0.0.1`, and `::1`.

## Error Model

Processing is best-effort. A failure in one stage is recorded in `error_details` and the service still returns a result object when possible.

Defined error codes:

- `INPUT_LOAD_ERROR`
- `STORAGE_ERROR`
- `VALIDATION_ERROR`
- `FACE_DETECTION_ERROR`
- `EXTRACTION_ERROR`
- `INTERNAL_ERROR`

Each `ProcessingError` contains:

- `code`
- `stage`
- `message`
- `retryable`

## Development

Run checks:

```bash
uv run ruff check .
uv run ty check src
uv run pytest -q
```

## Benchmarking Models

`passport-benchmark` runs the golden fixtures in `tests/fixtures/` against one or more Requesty-routed models and reports:

- strict field accuracy
- normalized Enjaz-style accuracy
- MRZ accuracy
- latency
- token usage
- estimated cost when pricing metadata is provided

Example:

```bash
passport-benchmark \
  --models "openai-responses/gpt-5-mini,google/gemini-3.1-flash-lite-preview" \
  --api-key "$PASSPORT_REQUESTY_API_KEY" \
  --pricing-json assets/pricing.json \
  --out-json benchmark_results.json
```

## Repository Layout

```text
passport-core/
├── assets/                  # template, face model, pricing metadata
├── src/passport_core/       # package code
├── tests/                   # unit and contract tests
├── agency-input/            # sample agency upload batch
└── benchmark_results.json   # sample benchmark output
```
