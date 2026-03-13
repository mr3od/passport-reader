# AGENTS.md - AI Assistant Guide for passport-reader

> **Purpose**: This file provides AI coding assistants with essential context about the passport-reader codebase, including project structure, development patterns, testing guidelines, and package-specific guidance.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Directory Structure](#directory-structure)
3. [Development Setup](#development-setup)
4. [Coding Patterns](#coding-patterns)
5. [Testing Guidelines](#testing-guidelines)
6. [Package-Specific Guidance](#package-specific-guidance)
7. [Common Tasks](#common-tasks)
8. [Deployment](#deployment)
9. [Troubleshooting](#troubleshooting)

---

## Project Overview

**passport-reader** is a multi-package Python monorepo for automated Yemeni passport processing with Telegram bot integration.

### Architecture

Three-layer design:
1. **passport-core**: Processing engine (validation, face detection, LLM extraction)
2. **passport-platform**: Application services (users, quotas, uploads, usage tracking)
3. **passport-telegram**: Telegram bot adapter

### Key Technologies
- Python 3.12+
- OpenCV (SIFT validation, YuNet face detection)
- Requesty AI (LLM routing)
- python-telegram-bot
- SQLite (via passport-platform)
- Docker + Kubernetes (MicroK8s)

---

## Directory Structure

```
passport-reader/
├── passport-core/              # Core processing engine
│   ├── src/passport_core/      # Package source
│   │   ├── workflow.py         # ⭐ Public adapter API
│   │   ├── pipeline.py         # Internal CLI orchestration
│   │   ├── vision.py           # Validation, detection, cropping
│   │   ├── llm.py              # LLM extraction
│   │   ├── io.py               # Image loading, storage
│   │   ├── models.py           # Data models
│   │   ├── config.py           # Settings
│   │   └── errors.py           # Exceptions
│   ├── tests/                  # Unit and contract tests
│   ├── assets/                 # ML models and templates
│   └── pyproject.toml          # Dependencies
│
├── passport-platform/          # Application services
│   ├── src/passport_platform/
│   │   ├── services/           # ⭐ Business logic services
│   │   │   ├── processing.py   # Main processing orchestration
│   │   │   ├── users.py        # User management
│   │   │   ├── quotas.py       # Quota enforcement
│   │   │   └── uploads.py      # Upload tracking
│   │   ├── repositories/       # Data access layer
│   │   ├── models/             # Domain models
│   │   ├── schemas/            # Commands and results
│   │   ├── policies/           # Plan policies
│   │   ├── db.py               # Database connection
│   │   ├── config.py           # Settings
│   │   └── enums.py            # Enumerations
│   ├── tests/                  # Service tests
│   ├── migrations/             # SQL migrations
│   └── pyproject.toml
│
├── passport-telegram/          # Telegram bot
│   ├── src/passport_telegram/
│   │   ├── bot.py              # ⭐ Bot handlers and logic
│   │   ├── messages.py         # Arabic message formatting
│   │   ├── config.py           # Settings
│   │   └── cli.py              # Entry point
│   ├── tests/                  # Bot tests
│   └── pyproject.toml
│
├── k8s/                        # Kubernetes manifests
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml.template
│   ├── pvc.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── ingress.yaml
│
├── .github/workflows/          # CI/CD
│   ├── deploy.yml              # Production deployment
│   └── test-build.yml          # PR build testing
│
├── Dockerfile                  # Multi-stage production build
├── deploy.sh                   # Deployment automation
├── validate-setup.sh           # Pre-deployment validation
└── .agents/summary/            # Generated documentation
    ├── index.md                # ⭐ Knowledge base index
    ├── architecture.md
    ├── components.md
    ├── interfaces.md
    ├── data_models.md
    ├── workflows.md
    └── dependencies.md
```

### Key Files to Know

**Public APIs**:
- `passport-core/src/passport_core/workflow.py` - Adapter-facing API
- `passport-platform/src/passport_platform/services/` - Application services
- `passport-telegram/src/passport_telegram/bot.py` - Bot handlers

**Configuration**:
- `passport-core/.env.example` - Core settings template
- `passport-platform/.env.example` - Platform settings template
- `passport-telegram/.env.example` - Bot settings template
- `k8s/configmap.yaml` - Production configuration

**Testing**:
- `passport-core/tests/` - Core tests with golden samples
- `passport-platform/tests/` - Service tests with fakes
- `passport-telegram/tests/` - Bot handler tests

---

## Development Setup

### Prerequisites
- Python 3.12+
- uv (recommended) or pip
- Docker (for containerization)
- MicroK8s (for deployment)

### Quick Start

```bash
# Clone and setup passport-core
cd passport-core
uv venv --python 3.12
source .venv/bin/activate
uv sync --extra dev
cp .env.example .env
# Set PASSPORT_REQUESTY_API_KEY in .env

# Setup passport-platform
cd ../passport-platform
uv venv --python 3.12
source .venv/bin/activate
uv sync --extra dev
cp .env.example .env

# Setup passport-telegram
cd ../passport-telegram
uv venv --python 3.12
source .venv/bin/activate
uv sync --extra dev
cp .env.example .env
# Set PASSPORT_TELEGRAM_BOT_TOKEN and ENV_FILE paths in .env

# Run tests
cd ../passport-core && uv run pytest -q
cd ../passport-platform && uv run pytest -q
cd ../passport-telegram && uv run pytest -q

# Run bot locally
cd ../passport-telegram
uv run passport-telegram
```

### Environment Variables

**passport-core** (prefix: `PASSPORT_`):
- `PASSPORT_REQUESTY_API_KEY` - Required for LLM extraction
- `PASSPORT_TEMPLATE_PATH` - Passport template for validation
- `PASSPORT_FACE_MODEL_PATH` - YuNet ONNX model
- `PASSPORT_STORAGE_BACKEND` - `local` or `s3`
- `PASSPORT_DATA_STORE_BACKEND` - `sqlite`, `json`, or `csv`
- `PASSPORT_LLM_MODEL` - Default: `openai-responses/gpt-5-mini`

**passport-platform** (prefix: `PASSPORT_PLATFORM_`):
- `PASSPORT_PLATFORM_DB_PATH` - SQLite database path

**passport-telegram** (prefix: `PASSPORT_TELEGRAM_`):
- `PASSPORT_TELEGRAM_BOT_TOKEN` - Required Telegram bot token
- `PASSPORT_TELEGRAM_CORE_ENV_FILE` - Path to core .env
- `PASSPORT_TELEGRAM_PLATFORM_ENV_FILE` - Path to platform .env
- `PASSPORT_TELEGRAM_ALLOWED_CHAT_IDS` - Optional CSV of allowed chat IDs

---

## Coding Patterns

### Package Imports

**passport-core** - Use public API:
```python
# ✅ Correct - Public API
from passport_core import (
    PassportWorkflow,
    PassportWorkflowResult,
    PassportData,
    Settings,
)

# ❌ Avoid - Internal implementation
from passport_core.pipeline import PassportCoreService
```

**passport-platform** - Use services, not repositories:
```python
# ✅ Correct - Service layer
from passport_platform import (
    ProcessingService,
    UserService,
    QuotaService,
    UploadService,
)

# ❌ Avoid - Direct repository access
from passport_platform.repositories import UsersRepository
```

### Configuration Pattern

All packages use Pydantic Settings:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_key: str
    log_level: str = "INFO"
    
    class Config:
        env_prefix = "PASSPORT_"
        env_file = ".env"

# Usage
settings = Settings()
```

### Error Handling Pattern

**passport-core** - Raises exceptions for unexpected errors:
```python
try:
    result = workflow.process_source("image.jpg")
    if result.is_complete:
        # Success - all stages completed
        print(result.data.PassportNumber)
    else:
        # Partial result - validation or detection failed
        if not result.validation.is_passport:
            print("Not a passport")
        elif not result.has_face_crop:
            print("No face detected")
except InputLoadError:
    # Handle load failure
    pass
```

**passport-platform** - Raises domain exceptions:
```python
from passport_platform import (
    ProcessingService,
    QuotaExceededError,
    UserBlockedError,
)

try:
    result = service.process_bytes(command)
except QuotaExceededError as e:
    # Handle quota exceeded
    print(f"Remaining: {e.quota_decision.uploads_remaining}")
except UserBlockedError:
    # Handle blocked user
    pass
```

### Service Pattern

Services encapsulate business logic:

```python
class UserService:
    def __init__(self, users: UsersRepository):
        self._users = users
    
    def get_or_create_user(self, command: EnsureUserCommand) -> User:
        # Business logic here
        user = self._users.get_by_external_identity(...)
        if user is None:
            user = self._users.create(...)
        return user
```

### Repository Pattern

Repositories handle data access:

```python
class UsersRepository:
    def __init__(self, conn: Connection):
        self._conn = conn
    
    def get_by_id(self, user_id: int) -> User | None:
        cursor = self._conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        return self._row_to_user(row) if row else None
```

### Workflow Pattern

Stage-by-stage processing:

```python
workflow = PassportWorkflow(settings=settings)

# High-level API
result = workflow.process_source("image.jpg")

# Or stage-by-stage
loaded = workflow.load_source("image.jpg")
validation = workflow.validate_passport(loaded)
face = workflow.detect_face(loaded, validation.page_quad)
crop = workflow.crop_face(loaded, face.bbox_original)
data = workflow.extract_data(loaded)
```

---

## Testing Guidelines

### Test Organization

**passport-core**:
- `test_workflow.py` - Workflow API tests
- `test_pipeline.py` - Pipeline service tests
- `test_vision.py` - Validation, detection, cropping tests
- `test_llm.py` - Extraction tests
- `test_io.py` - Loading and storage tests
- `test_contract_golden_samples.py` - Golden sample validation
- `test_benchmark.py` - Benchmarking tests

**passport-platform**:
- `test_processing_service.py` - Processing orchestration tests
- `test_user_service.py` - User management tests
- `test_quota_service.py` - Quota enforcement tests
- `test_upload_service.py` - Upload tracking tests

**passport-telegram**:
- `test_messages.py` - Message formatting tests
- `test_config.py` - Configuration tests

### Testing Patterns

**Unit Tests with Mocks**:
```python
def test_validator_rejects_blank():
    validator = PassportFeatureValidator(...)
    result = validator.validate(blank_image)
    assert not result.is_passport
```

**Integration Tests with Fakes**:
```python
class FakeWorkflow:
    def process_bytes(self, ...):
        return PassportWorkflowResult(...)

def test_processing_service():
    service = ProcessingService(
        users=user_service,
        quotas=quota_service,
        uploads=upload_service,
        workflow=FakeWorkflow()
    )
    result = service.process_bytes(command)
    assert result.success
```

**Contract Tests with Golden Samples**:
```python
def test_golden_fixtures_are_loadable():
    samples = load_ground_truth("tests/fixtures/golden.csv")
    assert len(samples) > 0
    for sample in samples:
        assert sample.image_path.exists()
```

### Running Tests

```bash
# Run all tests
uv run pytest -q

# Run specific test file
uv run pytest tests/test_workflow.py -v

# Run with coverage
uv run pytest --cov=passport_core --cov-report=html

# Run linter
uv run ruff check .

# Run type checker
uv run ty check src
```

### Test Fixtures

**passport-core** uses golden samples in `tests/fixtures/`:
- `abdullah_passport.jpg`
- `salem_passport.jpeg`
- `fatima_passport.jpeg`
- `lana_passport.jpeg`
- `omar_abdul_passport.jpg`
- `golden.csv` - Expected extraction results

**Fixture Usage**:
```python
@pytest.fixture
def sample_jpeg_bytes():
    path = Path(__file__).parent / "fixtures" / "abdullah_passport.jpg"
    return path.read_bytes()

def test_process_bytes(sample_jpeg_bytes):
    workflow = PassportWorkflow(settings=Settings())
    result = workflow.process_bytes(
        sample_jpeg_bytes,
        filename="test.jpg",
        mime_type="image/jpeg",
        source="test://source"
    )
    assert result.is_complete
```

---

## Package-Specific Guidance

### passport-core

**Purpose**: Core passport processing engine

**Key Responsibilities**:
- Passport validation using SIFT feature matching
- Face detection using YuNet ONNX model
- Face cropping with bounding box mapping
- LLM-based field extraction via Requesty
- Binary artifact storage (local/S3)
- Result persistence (SQLite/JSON/CSV)

**Public API** (`workflow.py`):
- `PassportWorkflow` - Main processing class
- `PassportWorkflowResult` - Unified result
- `PassportData` - Extracted fields
- `Settings` - Configuration

**Internal** (don't import directly):
- `PassportCoreService` - CLI pipeline
- `pipeline.py` - Internal orchestration

**Adding New Features**:
1. Add to `workflow.py` if adapter-facing
2. Add to `pipeline.py` if CLI-only
3. Update tests in `tests/`
4. Update models in `models.py` if needed

**Common Modifications**:
- Add extraction fields: Update `PassportData` in `models.py`
- Change validation: Modify `PassportFeatureValidator` in `vision.py`
- Add storage backend: Extend `BinaryStore` in `io.py`

---

### passport-platform

**Purpose**: Shared application services

**Key Responsibilities**:
- User management with external identity mapping
- Plan policies (Free, Pro, Enterprise)
- Monthly quota enforcement
- Upload tracking and status management
- Usage ledger accounting
- Processing orchestration

**Public API** (`services/`):
- `ProcessingService` - Main orchestration
- `UserService` - User management
- `QuotaService` - Quota enforcement
- `UploadService` - Upload tracking

**Database** (`db.py`):
- SQLite connection management
- Transaction support
- Schema initialization

**Adding New Features**:
1. Add service in `services/` for business logic
2. Add repository in `repositories/` for data access
3. Add models in `models/` for domain objects
4. Add schemas in `schemas/` for commands/results
5. Update migrations in `migrations/` for schema changes
6. Add tests in `tests/`

**Common Modifications**:
- Add plan: Update `PlanPolicy` in `policies/plans.py`
- Add usage type: Update `UsageEventType` in `enums.py`
- Add user field: Update `User` model and migration

---

### passport-telegram

**Purpose**: Telegram bot adapter

**Key Responsibilities**:
- Telegram bot interface
- Media group collection and batching
- Image download and validation
- Arabic response formatting
- Chat authorization

**Key Files**:
- `bot.py` - Bot handlers and logic
- `messages.py` - Arabic message formatting
- `config.py` - Settings

**Bot Handlers**:
- `start_command` - Welcome message
- `help_command` - Help text
- `image_message_handler` - Process images
- `telegram_error_handler` - Error handling

**Adding New Features**:
1. Add handler in `bot.py`
2. Add message formatter in `messages.py`
3. Update settings in `config.py` if needed
4. Add tests in `tests/`

**Common Modifications**:
- Add command: Add handler function and register in `build_application`
- Change messages: Update formatters in `messages.py`
- Add authorization: Modify `_is_allowed_chat` in `bot.py`

---

## Common Tasks

### Add New Passport Field

1. Update `PassportData` in `passport-core/src/passport_core/models.py`:
```python
class PassportData(BaseModel):
    # ... existing fields
    NewField: str | None = None
```

2. Update extraction prompt in `passport-core/src/passport_core/llm.py`:
```python
EXTRACTION_RULES = """
...
- NewField: Description of field
"""
```

3. Update message formatter in `passport-telegram/src/passport_telegram/messages.py`:
```python
def format_success_text(data: PassportData) -> str:
    # ... existing fields
    _value("الحقل الجديد", data.NewField),
```

4. Add tests for new field

---

### Add New Plan

1. Update `PlanName` enum in `passport-platform/src/passport_platform/enums.py`:
```python
class PlanName(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    NEW_PLAN = "new_plan"
```

2. Add policy in `passport-platform/src/passport_platform/policies/plans.py`:
```python
def get_plan_policy(plan: PlanName) -> PlanPolicy:
    policies = {
        # ... existing plans
        PlanName.NEW_PLAN: PlanPolicy(
            name=PlanName.NEW_PLAN,
            monthly_upload_limit=500,
            monthly_success_limit=250,
        ),
    }
    return policies[plan]
```

3. Add tests for new plan

---

### Add New Bot Command

1. Add handler in `passport-telegram/src/passport_telegram/bot.py`:
```python
async def new_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /new command"""
    await update.message.reply_text("Response text")
```

2. Register handler in `build_application`:
```python
application.add_handler(CommandHandler("new", new_command))
```

3. Update help text in `messages.py`:
```python
def help_text() -> str:
    return """
    ...
    /new - Description of new command
    """
```

4. Add tests for new command

---

### Add Database Migration

1. Create migration file in `passport-platform/migrations/`:
```sql
-- 0003_add_new_field.sql
ALTER TABLE users ADD COLUMN new_field TEXT;
CREATE INDEX idx_users_new_field ON users(new_field);
```

2. Update `Database.initialize()` to run new migration

3. Update repository to use new field

4. Add tests for migration

---

## Deployment

### Local Development

```bash
# Run bot locally
cd passport-telegram
uv run passport-telegram
```

### Docker Build

```bash
# Build from repository root
docker build -t passport-reader:latest .

# Run container
docker run --rm \
  --env-file passport-telegram/.env.production \
  -v passport-data:/data \
  passport-reader:latest
```

### Kubernetes Deployment

```bash
# Validate setup
./validate-setup.sh

# Full deployment
./deploy.sh deploy

# Or step-by-step
./deploy.sh build latest
./deploy.sh push latest
./deploy.sh apply
./deploy.sh restart

# Check status
./deploy.sh status

# View logs
./deploy.sh logs
./deploy.sh logs-follow

# Execute into pod
./deploy.sh exec
```

### CI/CD

**Automated Deployment**:
- Push to `main`, `production`, or tag triggers deployment
- GitHub Actions builds, pushes, and deploys automatically
- See `.github/workflows/deploy.yml`

**PR Testing**:
- PRs trigger Docker build test
- See `.github/workflows/test-build.yml`

---

## Troubleshooting

### Common Issues

**Import Errors**:
```bash
# Ensure packages are installed
cd passport-core && uv sync --extra dev
cd passport-platform && uv sync --extra dev
cd passport-telegram && uv sync --extra dev
```

**Missing API Key**:
```bash
# Set in .env file
echo "PASSPORT_REQUESTY_API_KEY=your_key" >> passport-core/.env
```

**Bot Not Responding**:
```bash
# Check bot token
echo $PASSPORT_TELEGRAM_BOT_TOKEN

# Check logs
./deploy.sh logs

# Check pod status
./deploy.sh status
```

**Database Errors**:
```bash
# Check database path
echo $PASSPORT_PLATFORM_DB_PATH

# Reinitialize database
rm data/platform.db
# Restart application to recreate
```

**Face Detection Fails**:
```bash
# Check model path
ls -la passport-core/assets/face_detection_yunet_2023mar.onnx

# Check OpenCV installation
python -c "import cv2; print(cv2.__version__)"
```

**Extraction Fails**:
```bash
# Check API key
curl -H "Authorization: Bearer $PASSPORT_REQUESTY_API_KEY" \
  https://router.requesty.ai/v1/models

# Check model name
echo $PASSPORT_LLM_MODEL
```

### Debug Mode

Enable debug logging:
```bash
export PASSPORT_LOG_LEVEL=DEBUG
export PASSPORT_PLATFORM_LOG_LEVEL=DEBUG
export PASSPORT_TELEGRAM_LOG_LEVEL=DEBUG
```

### Testing Specific Components

```bash
# Test validation only
uv run pytest tests/test_vision.py::test_validator_accepts_same_image -v

# Test extraction only
uv run pytest tests/test_llm.py -v

# Test quota service
uv run pytest tests/test_quota_service.py -v
```

---

## Additional Resources

**Comprehensive Documentation**:
- `.agents/summary/index.md` - Knowledge base index
- `.agents/summary/architecture.md` - System architecture
- `.agents/summary/components.md` - Component details
- `.agents/summary/interfaces.md` - API documentation
- `.agents/summary/data_models.md` - Data structures
- `.agents/summary/workflows.md` - Process workflows
- `.agents/summary/dependencies.md` - Dependencies

**Package READMEs**:
- `passport-core/README.md` - Core package documentation
- `passport-platform/README.md` - Platform package documentation
- `passport-telegram/README.md` - Telegram package documentation

**Deployment Documentation**:
- `START_HERE.md` - Getting started guide
- `DEPLOYMENT.md` - Deployment instructions
- `QUICKSTART.md` - Quick setup guide
- `ARCHITECTURE.md` - Architecture overview
- `k8s/README.md` - Kubernetes documentation

---

## Quick Reference

### Key Commands

```bash
# Development
uv sync --extra dev          # Install dependencies
uv run pytest -q             # Run tests
uv run ruff check .          # Lint code
uv run ty check src          # Type check

# Running
uv run passport-core process image.jpg    # Process image (CLI)
uv run passport-telegram                  # Run bot

# Deployment
./deploy.sh deploy           # Full deployment
./deploy.sh status           # Check status
./deploy.sh logs             # View logs
./deploy.sh restart          # Restart deployment
```

### Key Patterns

```python
# Process image (adapter API)
from passport_core import PassportWorkflow, Settings
workflow = PassportWorkflow(settings=Settings())
result = workflow.process_source("image.jpg")

# Process with platform services
from passport_platform import ProcessingService, ProcessUploadCommand
result = service.process_bytes(ProcessUploadCommand(...))

# Handle errors
from passport_platform import QuotaExceededError, UserBlockedError
try:
    result = service.process_bytes(command)
except QuotaExceededError as e:
    print(f"Quota exceeded: {e.quota_decision}")
except UserBlockedError:
    print("User is blocked")
```

---

**Last Updated**: 2026-03-13  
**Codebase Version**: commit c9b13e4  
**Documentation Version**: 1.0
