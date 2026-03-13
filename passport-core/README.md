# Passport Core

`passport-core` is the transport-neutral passport processing engine.

It owns only workflow concerns:

- image loading from bytes, files, and URLs
- passport-page validation
- face detection and cropping
- field extraction
- workflow result assembly

It does not own:

- artifact persistence
- application databases
- bot or API adapters
- batch-processing services

## Public API

Use the package root or [workflow.py](/Users/nexumind/Desktop/Github/passport-reader/passport-core/src/passport_core/workflow.py).

- `Settings`
- `LoadedImage`
- `BoundingBox`
- `ValidationResult`
- `FaceDetectionResult`
- `FaceCropResult`
- `PassportData`
- `PassportWorkflow`
- `PassportWorkflowResult`

## Workflow Result

`PassportWorkflow.process_source()` and `PassportWorkflow.process_bytes()` return `PassportWorkflowResult`.

Main fields:

- `loaded`
- `validation`
- `processed_loaded`
- `face`
- `face_crop`
- `data`

Convenience properties:

- `source`
- `filename`
- `mime_type`
- `image_bytes`
- `processed_image_bytes`
- `face_crop_bytes`
- `has_face_crop`
- `is_complete`

## Installation

```bash
cd passport-core
uv venv --python 3.12
source .venv/bin/activate
uv sync --extra dev
cp .env.example .env
```

Set at least:

```bash
export PASSPORT_REQUESTY_API_KEY=your_key_here
```

## Configuration

All settings use the `PASSPORT_` prefix.

Common settings:

- `PASSPORT_ASSETS_DIR`
- `PASSPORT_TEMPLATE_PATH`
- `PASSPORT_FACE_MODEL_PATH`
- `PASSPORT_HTTP_TIMEOUT_SECONDS`
- `PASSPORT_MAX_DOWNLOAD_BYTES`
- `PASSPORT_LLM_MODEL`
- `PASSPORT_REQUESTY_API_KEY`
- `PASSPORT_REQUESTY_BASE_URL`
- `PASSPORT_LOG_LEVEL`
- `PASSPORT_LOG_JSON`

See [passport-core/.env.example](/Users/nexumind/Desktop/Github/passport-reader/passport-core/.env.example) for the full workflow configuration.

## Python Usage

```python
from passport_core import PassportWorkflow, Settings

workflow = PassportWorkflow(settings=Settings())

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

Stage-by-stage usage:

```python
loaded = workflow.load_source("tests/fixtures/abdullah_passport.jpg")
validation = workflow.validate_passport(loaded)
face = workflow.detect_face(loaded, validation.page_quad)
crop = workflow.crop_face(loaded, face.bbox_original if face else None)
data = workflow.extract_data(loaded) if crop is not None else None
```

For byte uploads:

```python
result = workflow.process_bytes(
    image_bytes,
    filename="passport.jpg",
    mime_type="image/jpeg",
    source="telegram://file/123",
)
```

## Development

```bash
uv run ruff check .
uv run ty check src
uv run pytest -q
```

## Benchmarking

The package still exposes `passport-benchmark` for evaluation against golden fixtures.
