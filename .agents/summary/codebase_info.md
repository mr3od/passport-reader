# Codebase Information

## Project Overview

**passport-reader** is a multi-package Python monorepo for automated Yemeni passport processing. It validates passport images, detects and crops faces, extracts structured data using LLMs, and provides multiple transport adapters (Telegram bot, future HTTP API) with shared application services for user management, quotas, and usage tracking.

## Technology Stack

- **Language**: Python 3.12+
- **Package Manager**: uv (with pip fallback)
- **Computer Vision**: OpenCV (SIFT validation, YuNet face detection)
- **LLM Integration**: Requesty AI router (supports OpenAI, Google, Anthropic models)
- **Database**: SQLite (via `passport-platform`)
- **Messaging**: python-telegram-bot (PTB)
- **Containerization**: Docker (multi-stage builds)
- **Orchestration**: Kubernetes (MicroK8s)
- **CI/CD**: GitHub Actions

## Repository Structure

```
passport-reader/
├── passport-core/           # Core passport processing engine
│   ├── src/passport_core/   # Package source
│   ├── tests/               # Unit and contract tests
│   ├── assets/              # ML models and templates
│   └── agency-input/        # Sample test images
├── passport-platform/       # Shared application services
│   ├── src/passport_platform/
│   ├── tests/
│   └── migrations/          # SQLite schema migrations
├── passport-telegram/       # Telegram bot adapter
│   ├── src/passport_telegram/
│   └── tests/
├── k8s/                     # Kubernetes manifests
├── .github/workflows/       # CI/CD pipelines
├── Dockerfile               # Production multi-stage build
├── deploy.sh                # Deployment automation script
└── validate-setup.sh        # Pre-deployment validation
```

## Package Architecture

### Three-Layer Design

1. **passport-core** (Processing Engine)
   - Passport validation using SIFT feature matching
   - Face detection using YuNet ONNX model
   - Face cropping with bounding box mapping
   - LLM-based field extraction via Requesty
   - Binary artifact storage (local/S3)
   - Result persistence (SQLite/JSON/CSV)

2. **passport-platform** (Application Layer)
   - User management with external identity mapping
   - Plan policies (Free, Pro, Enterprise)
   - Monthly quota enforcement
   - Upload tracking and status management
   - Usage ledger accounting
   - Processing orchestration

3. **passport-telegram** (Transport Adapter)
   - Telegram bot interface
   - Media group collection
   - Image download and validation
   - Arabic response formatting
   - Chat authorization

## Programming Languages

- **Python**: 100% (all packages)
- **Shell**: Deployment and validation scripts
- **YAML**: Kubernetes manifests, GitHub Actions
- **SQL**: Database migrations
- **Dockerfile**: Container definitions

## Key Dependencies

### passport-core
- `opencv-python`: Image processing and face detection
- `pydantic-ai`: LLM extraction framework
- `httpx`: HTTP client for remote image loading
- `pillow`: Image encoding/decoding
- `python-dotenv`: Environment configuration

### passport-platform
- `pydantic`: Data validation and settings
- `pydantic-settings`: Environment-based configuration
- `structlog`: Structured logging

### passport-telegram
- `python-telegram-bot`: Telegram Bot API wrapper
- `apscheduler`: Media group collection scheduling

## Development Tools

- **Testing**: pytest
- **Linting**: ruff
- **Type Checking**: pyright (via `ty` alias)
- **Package Management**: uv
- **Containerization**: Docker
- **Orchestration**: MicroK8s (Kubernetes)

## Lines of Code

- **Total**: ~5,920 LOC
- **Functions**: 305
- **Classes**: 87
- **Prioritized Files**: 60 of 141 total files

## Recent Development Activity

Latest commits (most recent first):
1. `c9b13e4` - feat: route telegram processing through platform service
2. `30b9e73` - feat: add passport platform package
3. `5791881` - feat: add telegram bot adapter
4. `b93c3f0` - build: align default passport-core runtime setup
5. `8f62921` - refactor: expose adapter workflow api

## Deployment Infrastructure

- **Container Registry**: `registry.mohammed-alkebsi.dev`
- **Kubernetes Namespace**: `passport-reader`
- **Domain**: `*.mohammed-alkebsi.dev`
- **Deployment Strategy**: Recreate (single replica)
- **Persistent Storage**: 10GB PVC for data persistence
- **CI/CD**: Automated deployment on push to main/production branches

## Configuration Management

All packages use environment-based configuration with `.env` files:
- `passport-core/.env` - Core processing settings
- `passport-platform/.env` - Database and app settings
- `passport-telegram/.env` - Bot token and chat authorization

Production configuration uses Kubernetes ConfigMaps and Secrets.

## Testing Strategy

- **Unit Tests**: Component-level testing with mocks
- **Contract Tests**: Golden sample validation
- **Integration Tests**: Service-level testing with fake implementations
- **Benchmark Tests**: Model accuracy and performance evaluation

## Documentation Files

- Package READMEs: Detailed setup and usage per package
- Deployment docs: START_HERE.md, DEPLOYMENT.md, QUICKSTART.md
- Architecture: ARCHITECTURE.md with Mermaid diagrams
- CI/CD: CI_CD_REVIEW.md, GitHub workflow documentation
- Operations: deploy.sh, validate-setup.sh with inline help
