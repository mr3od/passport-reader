# passport-benchmark

Benchmark and evaluation suite for `passport-core` extraction.

## Setup

```bash
cd passport-benchmark
uv sync --all-extras
```

## Structure

```
passport-benchmark/
├── pyproject.toml
├── manifest.csv                         # Index of all cases
├── agency-input/                        # Raw images from travel agencies (unprocessed)
├── cases/
│   ├── labeled/                         # Cases WITH ground truth (ready to score)
│   │   ├── case_001/
│   │   │   ├── input.jpeg
│   │   │   └── expected.json            # Human-verified ground truth
│   │   └── ...
│   └── unlabeled/                       # Cases WITHOUT ground truth yet
│       ├── case_013/
│       │   ├── input.jpeg
│       │   └── expected.json            # Blank skeleton — fill this in
│       └── ...
├── src/passport_benchmark/
│   ├── mrz.py                           # MRZ parsing and check digit validation
│   ├── compare.py                       # Field comparison with Arabic normalization
│   ├── report.py                        # Report generation (Markdown + CSV)
│   ├── organize.py                      # CLI: raw images → case directories
│   ├── runner.py                        # CLI: run benchmark and score
│   ├── prompt_v2.py                     # Experimental 7-step extraction prompt
│   └── extractor_v2.py                  # Experimental v2 extractor
└── tests/
    ├── test_mrz.py
    └── test_compare.py
```

## Workflow

### 1. Organize new images

```bash
benchmark-organize agency-input/ cases/
```

New images go into `cases/unlabeled/case_NNN/` with a blank `expected.json` skeleton.

### 2. Label ground truth

Open each `cases/unlabeled/case_NNN/input.jpeg`, read the passport, fill in
`expected.json`. Then move the case to `cases/labeled/`:

```bash
mv cases/unlabeled/case_013 cases/labeled/case_013
```

Update `manifest.csv`: set `partition=labeled` and `ground_truth_status=done`.

### 3. Run the benchmark

```bash
# Score existing actual.json files against ground truth
benchmark-run cases/

# Or run the extractor first, then score
benchmark-run cases/ --extract
```

Outputs: `benchmark_report.md` and `benchmark_results.csv`.

### 4. Run tests

```bash
uv run pytest
uv run ruff check .
```

## Key test cases

| Case | What it tests |
|---|---|
| case_004 | Arabic name لناء for "Lana" — models may "correct" to لانا |
| case_005 | Arabic surname العكبري vs English AL-AKBARI — models assume الاكبري |
| case_007 | 4 given names — only 3 fit individual slots |
| case_008 | Socotri surname DKNZHR — non-Arabic, no standard transliteration |
| case_009 | FirstName = GrandfatherName = MOHAMMED — must not deduplicate |
| case_010 | FatherName = Surname = AMER — must not "correct" |
| case_012 | FatherName = Surname = KHAMIS — same pattern |

## V2 prompt design

The extraction prompt uses 7 explicit steps to eliminate black-box reasoning:

1. **Image assessment** — layout, quality, obstructions
2. **Structured data** — passport number, dates, country code
3. **Arabic fields from VIZ** — with "do NOT back-translate" rules
4. **MRZ extraction + parsing** — teaches the model MRZ structure
5. **English fields from VIZ**
6. **MRZ vs VIZ cross-validation** — signal priority hierarchy
7. **Arabic ↔ English consistency check**

The `extractor_v2.py` and `prompt_v2.py` modules are experimental.
Once validated, they move to `passport-core`.
