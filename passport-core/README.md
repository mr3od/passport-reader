# Passport Core

`passport-core` is the passport-processing package used for Yemeni travel-agency workflows.

It takes a passport image, validates that the page is really a passport, detects and crops the face, extracts structured fields with an LLM, and stores both the binary artifacts and the unified result record.

Pipeline:

`load -> store original -> validate -> detect face -> crop face -> extract fields -> store result`

## What It Produces

The public adapter API returns one `PassportWorkflowResult` per image with:

- `loaded`: original loaded image payload and metadata
- `validation`: passport match result and debug counters
- `face`: detected face bounding box
- `face_crop`: cropped face image payload
- `data`: extracted `PassportData`
- `is_complete`: `True` only when validation, face crop, and extraction all succeed

The internal CLI pipeline persists `PassportProcessingResult` records with stored artifact URIs and accumulated `error_details`.

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
- OpenCV with SIFT support
- an ONNX RetinaFace face detection model file
- `assets/passport_template_v2.jpg`
- `assets/face_detection_retinaface_mobile0.25.onnx` or another compatible model path set via `PASSPORT_FACE_MODEL_PATH`
- A Requesty API key in `PASSPORT_REQUESTY_API_KEY`

For headless servers and containers, `passport-core` uses `onnxruntime` with `opencv-python-headless` for face detection and image preprocessing.

The public package API is adapter-oriented. Use `PassportWorkflow` and the public models from the package root. `pipeline.py` remains internal CLI orchestration.

Package-root public API:

- `Settings`
- `LoadedImage`
- `BoundingBox`
- `ValidationResult`
- `FaceDetectionResult`
- `FaceCropResult`
- `PassportData`
- `PassportWorkflow`
- `PassportWorkflowResult`

## Installation

### With `uv`

```bash
cd passport-core
uv venv --python 3.12
source .venv/bin/activate
uv sync --extra dev
cp .env.example .env
```

### With `pip`

```bash
cd passport-core
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

Then set at least:

```bash
export PASSPORT_REQUESTY_API_KEY=your_key_here
```

The LLM extractor is part of the default install. You do not need an extra flag to run `passport-core`.

## Configuration

All settings use the `PASSPORT_` prefix and are loaded from environment variables or `.env`.

Common settings:

- `PASSPORT_TEMPLATE_PATH`: masked passport template used by SIFT validation
- `PASSPORT_FACE_MODEL_PATH`: RetinaFace ONNX model used for face detection
- `PASSPORT_FACE_NMS_THRESHOLD`: NMS threshold for RetinaFace detections
- `PASSPORT_FACE_INPUT_WIDTH`: RetinaFace input width when the ONNX model uses dynamic shapes
- `PASSPORT_FACE_INPUT_HEIGHT`: RetinaFace input height when the ONNX model uses dynamic shapes
- `PASSPORT_VALIDATOR_RANSAC_THRESHOLD`: homography RANSAC threshold for SIFT matching
- `PASSPORT_VALIDATOR_MIN_QUAD_AREA_RATIO`: minimum projected passport-page area ratio relative to the source image
- `PASSPORT_VALIDATOR_MAX_QUAD_AREA_RATIO`: maximum projected passport-page area ratio relative to the source image
- `PASSPORT_CANDIDATE_EARLY_STOP_VALIDATION_SCORE`: stop candidate search early after a strong passport match
- `PASSPORT_CANDIDATE_EARLY_STOP_FACE_SCORE`: stop candidate search early after a strong face detection
- `PASSPORT_CANDIDATE_EARLY_STOP_LANDMARK_SCORE`: stop candidate search early after a strong upright-landmark score
- `PASSPORT_CANDIDATE_MAX_EXTRACTION_ATTEMPTS`: maximum extracted candidates tried per image
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

The CLI uses an internal pipeline service for batch-oriented processing and persistence. Adapters should use `PassportWorkflow` instead of importing from `pipeline.py`.

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

`PassportWorkflow` is the public adapter-facing API.

```python
from passport_core import PassportWorkflow, Settings

settings = Settings()
workflow = PassportWorkflow(settings=settings)

try:
    result = workflow.process_source("tests/fixtures/abdullah_passport.jpg")

    print(result.validation.is_passport)
    print(result.face.bbox_original if result.face else None)
    print(result.face_crop.width if result.has_face_crop else None)
    print(result.data.PassportNumber if result.data else None)
    print(result.is_complete)
finally:
    workflow.close()
```

You can also process multiple sources:

```python
results = [
    workflow.process_source("tests/fixtures/abdullah_passport.jpg"),
    workflow.process_source("tests/fixtures/salem_passport.jpeg"),
]
```

For adapters that receive uploads as bytes:

```python
result = workflow.process_bytes(
    image_bytes,
    filename="passport.jpg",
    mime_type="image/jpeg",
    source="telegram://file/123",
)
```

Adapters can send the original image from `result.image_bytes` and the cropped face from `result.face_crop_bytes`.

If you want the best matched passport candidate, face metadata, and face crop without invoking the extractor yet:

```python
loaded = workflow.load_source("tests/fixtures/abdullah_passport.jpg")
prepared = workflow.prepare_loaded(loaded)

print(prepared.validation.is_passport)
print(prepared.face.bbox_original if prepared.face else None)
print(prepared.face_crop.width if prepared.face_crop else None)
```

If you want explicit stage-by-stage control:

```python
loaded = workflow.load_source("tests/fixtures/abdullah_passport.jpg")
validation = workflow.validate_passport(loaded)
face = workflow.detect_face(loaded, validation.page_quad)
crop = workflow.crop_face(loaded, face.bbox_original)
data = workflow.extract_data(loaded) if crop is not None else None
```

`PassportWorkflow.process_source()` and `process_bytes()` return partial results when validation fails or no face crop can be produced. Unexpected loader, validator, detector, or extractor exceptions still raise to the caller.

## Input Sources

`ImageLoader` accepts:

- local file paths
- remote `http` and `https` URLs

Remote downloads are limited by `PASSPORT_MAX_DOWNLOAD_BYTES` and reject localhost-style hosts such as `localhost`, `127.0.0.1`, and `::1`.

## Error Model

`ProcessingError` and `PassportProcessingResult.error_details` are part of the internal CLI pipeline contract. The public adapter workflow API raises exceptions for unexpected failures instead of accumulating error records.

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
│   ├── workflow.py          # public adapter-facing API
│   └── pipeline.py          # internal CLI orchestration
├── tests/                   # unit and contract tests
├── agency-input/            # sample agency upload batch
└── benchmark_results.json   # sample benchmark output
```
