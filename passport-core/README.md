# Passport Core

Core passport processing pipeline:

`load -> validate -> align -> detect face -> extract -> store`

## Quickstart

```bash
cd passport-core
uv venv --python 3.12
source .venv/bin/activate
uv sync --all-extras --dev
cp .env.example .env
uv run pytest -q
```

The masked template is expected at `assets/passport_template_v2.jpg`.
