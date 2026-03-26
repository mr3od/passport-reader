# Runtime Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate env, container, and production deployment assets into one root workspace contract with host-based local development and declarative-first MicroK8s production.

**Architecture:** Create one root local env example and one root production env example, remove duplicate package/runtime artifacts, keep one root multi-stage image build, and move production truth into a root `k8s/` manifest set. Keep CI thin by applying manifests and updating image tags instead of patching deployment structure inline.

**Tech Stack:** Python 3.12, `uv`, Docker multi-stage builds, MicroK8s, Kubernetes Deployments/Services/PVCs/Secrets, GitHub Actions

---

## File Map

**Create:**
- `.env.example`
- `k8s/namespace.yaml`
- `k8s/pvc.yaml`
- `k8s/api-deployment.yaml`
- `k8s/api-service.yaml`
- `k8s/telegram-deployment.yaml`
- `docs/superpowers/plans/2026-03-27-runtime-consolidation.md`

**Modify:**
- `.env.production.example`
- `Dockerfile`
- `.github/workflows/deploy.yml`
- `passport-core/README.md`
- `passport-platform/README.md`
- `passport-api/README.md`
- `passport-telegram/README.md`
- `passport-benchmark/README.md`

**Remove:**
- `docker-compose.yml`
- `passport-core/.env.example`
- `passport-platform/.env.example`
- `passport-api/.env.example`
- `passport-telegram/.env.example`
- `passport-telegram/.env.production.example`
- `passport-telegram/Dockerfile`
- `deploy.sh` if CI fully replaces it

### Task 1: Consolidate Env Contracts

**Files:**
- Create: `.env.example`
- Modify: `.env.production.example`
- Remove: `passport-core/.env.example`
- Remove: `passport-platform/.env.example`
- Remove: `passport-api/.env.example`
- Remove: `passport-telegram/.env.example`
- Remove: `passport-telegram/.env.production.example`

- [ ] **Step 1: Create the root local env example with all maintained runtime settings**
- [ ] **Step 2: Ensure the root production env example matches the current shared production contract**
- [ ] **Step 3: Remove package env example files once docs and code no longer require them**
- [ ] **Step 4: Verify all current `PASSPORT_*` settings used in code are represented in one of the root env examples**
- [ ] **Step 5: Commit the env consolidation**

### Task 2: Consolidate the Root Build Artifact

**Files:**
- Modify: `Dockerfile`
- Remove: `passport-telegram/Dockerfile`

- [ ] **Step 1: Make the root multi-stage Dockerfile explicitly workspace-aware**
- [ ] **Step 2: Ensure it installs the maintained workspace packages into one runtime image**
- [ ] **Step 3: Remove the package-specific Telegram Dockerfile**
- [ ] **Step 4: Build the root image locally to verify the consolidated contract**
- [ ] **Step 5: Commit the Docker consolidation**

### Task 3: Add Declarative MicroK8s Manifests

**Files:**
- Create: `k8s/namespace.yaml`
- Create: `k8s/pvc.yaml`
- Create: `k8s/api-deployment.yaml`
- Create: `k8s/api-service.yaml`
- Create: `k8s/telegram-deployment.yaml`

- [ ] **Step 1: Create a namespace manifest for `passport-reader`**
- [ ] **Step 2: Create one PVC manifest for `/data`**
- [ ] **Step 3: Create an API Deployment manifest with shared secret env, data mount, resource bounds, and non-root security context**
- [ ] **Step 4: Create an API Service manifest**
- [ ] **Step 5: Create a Telegram Deployment manifest with shared secret env, data mount, resource bounds, and non-root security context**
- [ ] **Step 6: Validate the manifests with client-side dry-run semantics**
- [ ] **Step 7: Commit the Kubernetes manifests**

### Task 4: Make Deployment Declarative-First

**Files:**
- Modify: `.github/workflows/deploy.yml`
- Remove: `deploy.sh` if no longer needed

- [ ] **Step 1: Remove inline structural patch logic from the deploy workflow**
- [ ] **Step 2: Keep only rsync, image build/import, secret upsert, `kubectl apply`, image tag update, rollout status, and logs**
- [ ] **Step 3: Remove `deploy.sh` if the workflow fully owns the remaining deployment steps**
- [ ] **Step 4: Verify the workflow text references `k8s/` as the production source of truth**
- [ ] **Step 5: Commit the deployment-flow simplification**

### Task 5: Remove Unsupported Local Orchestration and Update Docs

**Files:**
- Remove: `docker-compose.yml`
- Modify: `passport-core/README.md`
- Modify: `passport-platform/README.md`
- Modify: `passport-api/README.md`
- Modify: `passport-telegram/README.md`
- Modify: `passport-benchmark/README.md`

- [ ] **Step 1: Remove `docker-compose.yml`**
- [ ] **Step 2: Update package READMEs to use root `.env`, root `.env.production`, and `uv run ...` from the workspace root**
- [ ] **Step 3: Remove any README guidance that still teaches package-local env setup as the default path**
- [ ] **Step 4: Verify docs no longer reference removed package env files or Compose**
- [ ] **Step 5: Commit the documentation cleanup**

### Task 6: Verify End-to-End Runtime Consolidation

**Files:**
- Verify: `.env.example`
- Verify: `.env.production.example`
- Verify: `Dockerfile`
- Verify: `k8s/*.yaml`
- Verify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Run a repo-wide search to confirm removed env/docker artifacts are no longer documented as supported paths**
- [ ] **Step 2: Build the root Docker image**
- [ ] **Step 3: Validate Kubernetes manifests with `kubectl apply --dry-run=client` or `microk8s kubectl apply --dry-run=client` if available**
- [ ] **Step 4: Verify root `uv run passport-api` and `uv run passport-telegram` still reflect the supported local workflow**
- [ ] **Step 5: Append `docs/HISTORY.md` with the runtime consolidation entry**
- [ ] **Step 6: Commit the final consolidated runtime state**

## Self-Review

### Spec coverage
- Root env consolidation: Task 1.
- Root image only: Task 2.
- Declarative `k8s/` production truth: Task 3.
- Declarative-first CI flow: Task 4.
- No local orchestration: Task 5.
- Final verification and history entry: Task 6.

### Placeholder scan
- No TODO/TBD markers remain.
- Each task names exact files and concrete outcomes.

### Type and naming consistency
- Root env files are consistently `.env.example` and `.env.production.example`.
- Production manifests consistently live under `k8s/`.
- API and Telegram remain separate Deployments using one shared image.
