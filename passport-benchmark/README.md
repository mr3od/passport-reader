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
# Score an existing run
benchmark-run cases/ --run-id <run-id>

# Run extraction then score
benchmark-run cases/ --extract --run-id <run-id>
benchmark-run cases/ --extract --model google/gemini-3.1-flash-lite-preview

# Organize raw images into case directories
benchmark-organize <images-dir> cases/

# Draft expected.json for unlabeled cases
benchmark-draft-unlabeled cases/
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
cd passport-benchmark
uv sync --extra dev
```

Requires `passport-core` `.env` with `PASSPORT_REQUESTY_API_KEY` for `--extract` mode.
