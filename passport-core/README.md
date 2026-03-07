# Passport Core

Core passport processing pipeline:

`load -> validate -> detect face -> extract -> store`

## Quickstart

```bash
cd passport-core
uv venv --python 3.12
source .venv/bin/activate
uv sync --all-extras --dev
cp .env.example .env
uv run ty check src
uv run pytest -q
```

The masked template is expected at `assets/passport_template_v2.jpg`.

LLM extraction uses `pydantic-ai` against Requesty's OpenAI-compatible endpoint.
Set `PASSPORT_REQUESTY_API_KEY` in `.env`.
Structured schema output is enforced via `output_type=PassportData`.

## Benchmark models

Use the golden fixtures to compare models for accuracy, speed, and cost:

```bash
passport-benchmark \
  --models "openai-responses/gpt-5-mini,google/gemini-3.1-flash-lite-preview" \
  --api-key "$PASSPORT_REQUESTY_API_KEY" \
  --pricing-json pricing.json \
  --out-json benchmark_results.json
```

`pricing.json` example:

```json
{
  "openai-responses/gpt-5-mini": { "input_per_1m": 0.15, "output_per_1m": 0.6 },
  "google/gemini-3.1-flash-lite-preview": { "input_per_1m": 0.1, "output_per_1m": 0.4 }
}
```
