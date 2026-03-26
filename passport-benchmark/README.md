# Passport Benchmark

Evaluation suite for `passport-core` extraction. Scores extractor output against labeled ground truth.

## Structure

```
cases/
├── labeled/          # Ground truth cases (expected.json + input.jpeg)
│   └── case_NNN/
└── unlabeled/        # Images pending labeling
runs/                 # Extraction outputs and reports per run
```

## CLI

```bash
uv run benchmark-run cases/ --run-id <run-id>
uv run benchmark-run cases/ --extract --run-id <run-id>
uv run benchmark-run cases/ --extract --model google/gemini-3.1-flash-lite-preview
uv run benchmark-organize <images-dir> cases/
uv run benchmark-draft-unlabeled cases/
```

## Installation

```bash
# from the repository root
cp .env.example .env
uv sync --all-packages
```

Use the root `.env.example` and copy it to the repository root `.env`.
Requires `PASSPORT_REQUESTY_API_KEY` in the root `.env` for `--extract` mode.

## Development

```bash
uv run pytest passport-benchmark/tests -q
uv run ruff check passport-benchmark/src passport-benchmark/tests
uv run ty check passport-benchmark/src
```
