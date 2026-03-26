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

## Scoring

Each field is classified as: `match`, `misread`, `omission`, `hallucination`, or `both_null`.

Arabic fields are compared with normalization (alef variants, tashkeel, taa marbuta). MRZ lines are compared with trailing-filler tolerance. English fields are case-insensitive.

Reports (markdown + CSV) are written to the run directory.

## Adding cases

1. Place `input.jpeg` in `cases/unlabeled/case_NNN/`
2. Run `benchmark-draft-unlabeled cases/` to generate a starter `expected.json`
3. Verify and correct the draft manually
4. Move the case to `cases/labeled/`
5. Update `manifest.csv`

## Installation

```bash
uv sync --all-packages
```

Requires `passport-core/.env` with `PASSPORT_REQUESTY_API_KEY` for `--extract` mode.
