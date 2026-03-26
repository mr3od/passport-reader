# Runtime Consolidation Design

## Goal

Consolidate runtime configuration, container build assets, and deployment assets into one root workspace contract while keeping local development host-based with `uv run ...` and using MicroK8s as the only production orchestration platform.

## Scope

In scope:
- one root `.env.example` for local development
- one root `.env.production.example` for production
- one root multi-stage `Dockerfile`
- one root deployment script
- one root `k8s/` directory as the production source of truth
- removing local orchestration assets that are no longer part of the intended workflow
- updating docs and package defaults to use the root workspace contract

Out of scope:
- introducing Helm, Kustomize, or another higher-level deployment tool
- creating separate images for API and Telegram
- adding local Kubernetes or Docker orchestration for development
- changing package boundaries or merging Python distributions

## Current State

The repository currently mixes multiple operational contracts:
- root-level `.env.production` and `.env.production.example`
- package-level `.env.example` files under `passport-core`, `passport-platform`, `passport-api`, and `passport-telegram`
- a root `Dockerfile`
- a package-specific `passport-telegram/Dockerfile`
- a root `docker-compose.yml`
- a root `deploy.sh`
- a GitHub workflow that performs MicroK8s deployment logic inline instead of applying versioned manifests

This creates duplicated sources of truth for configuration and deployment.

## Decision

Use one root workspace runtime contract.

### Local development

Local development uses host-based commands from the repository root:
- `uv run passport-api`
- `uv run passport-telegram`
- `uv run pytest ...`

There is no local Docker Compose workflow and no local Kubernetes workflow as part of the supported development path.

### Production

Production uses MicroK8s only.

The root `k8s/` directory becomes the versioned source of truth for production resources. The deployment path should be declarative-first: manifests define runtime structure, while CI performs only the small imperative steps that remain unavoidable, such as image import, secret upsert, image tag update, and rollout verification.

## Environment Contract

### Root local env file

The repository should expose one root `.env.example` for development.

It should include all maintained runtime settings needed by:
- `passport-core`
- `passport-platform`
- `passport-api`
- `passport-telegram`

Developers should copy it to a root `.env` and run services from the repository root.

### Root production env file

The repository should expose one root `.env.production.example` for production.

The real server-side `.env.production` remains outside version control and is the source for the Kubernetes runtime secret.

### Package env files

Package-level `.env.example` files are no longer the source of truth.

Preferred outcome:
- remove package-level `.env.example` files if code and docs no longer require them

Acceptable fallback if needed:
- keep minimal compatibility shims temporarily, but documentation must point to the root env files only

## Build Contract

### Root image

Keep one root multi-stage `Dockerfile`.

It should:
- build from the workspace root
- copy root packaging metadata needed for dependency resolution
- copy maintained package source trees and assets
- produce one runtime image that can run both API and Telegram

Service behavior should differ by Kubernetes container command, not by separate Dockerfiles or separate images.

### Remove package-specific Dockerfiles

`passport-telegram/Dockerfile` should be removed once the root Dockerfile fully replaces it.

## Kubernetes Production Structure

Create a root `k8s/` directory.

Recommended initial manifest set:
- `k8s/namespace.yaml`
- `k8s/pvc.yaml`
- `k8s/api-deployment.yaml`
- `k8s/api-service.yaml`
- `k8s/telegram-deployment.yaml`

Optional if needed during implementation:
- `k8s/secret.example.yaml` or a documented secret-generation path

### Shared production assumptions

- one namespace, such as `passport-reader`
- one shared image imported into MicroK8s
- one shared secret sourced from `.env.production`
- one shared PVC mounted at `/data`
- one Service for API
- no Service for Telegram unless a concrete operational need appears

### Kubernetes best practices to apply

The manifests should follow standard production practices:
- explicit labels
- resource requests and limits
- non-root security context
- appropriate restart behavior
- readiness and liveness probes where the application supports them
- consistent naming across resources

## Deployment Flow

### Declarative-first deployment path

Production truth should live in versioned Kubernetes manifests under `k8s/`.

The deployment flow should be:
- build the root image
- import the image into MicroK8s
- upsert the runtime secret from `.env.production`
- apply the versioned manifests from `k8s/`
- update Deployment image tags if image names are not committed directly in manifests
- wait for rollout and run verification commands

### Root deploy script

`deploy.sh` should be reduced to a thin helper or removed entirely if CI can express the remaining deployment steps cleanly.

The repository should not keep a large imperative deployment script that duplicates production structure already encoded in manifests.

### GitHub workflow

The GitHub Actions deploy workflow should become the primary orchestration layer for the remaining small imperative steps.

It should:
- sync code to the server
- build and import the image
- upsert the runtime secret
- apply `k8s/`
- update image tags where needed
- wait for rollout and verify

It should not keep detailed structural deployment mutation logic inline when that structure belongs in versioned manifests.

## Files Expected to Change

Root files:
- `.env.example` (new)
- `.env.production.example`
- `Dockerfile`
- `deploy.sh` (likely simplified heavily or removed)
- `.github/workflows/deploy.yml`
- remove `docker-compose.yml`

Package/runtime files likely affected:
- `passport-api/.env.example`
- `passport-core/.env.example`
- `passport-platform/.env.example`
- `passport-telegram/.env.example`
- `passport-telegram/.env.production.example`
- remove `passport-telegram/Dockerfile`

Docs likely affected:
- package README files that still mention package-local env setup
- possibly root docs for deployment workflow if present

New production assets:
- `k8s/namespace.yaml`
- `k8s/pvc.yaml`
- `k8s/api-deployment.yaml`
- `k8s/api-service.yaml`
- `k8s/telegram-deployment.yaml`

## Risks

### Path assumptions in code

Some package config defaults currently assume package-local `.env` files or package-relative paths. The migration must verify root-based execution still resolves all required files correctly.

### Shared env exposure

Using one shared production secret means both deployments receive the same env set. This is acceptable for the current architecture, but it should be recognized as a deliberate trade-off.

### Kubernetes manifest drift

If deployment behavior remains partially embedded in CI and partially embedded in manifests, drift will persist. The migration must move production truth into `k8s/` and keep CI limited to image and secret handling plus rollout verification.

### Persistent data handling

The `/data` mount must remain consistent across deployments so SQLite and artifacts continue to work as expected.

## Verification Plan

Minimum verification for this consolidation:
- root `.env.example` covers all maintained runtime settings still used by code
- package docs point to root env files and root `uv run` workflow
- root Docker build succeeds
- Kubernetes manifests validate with client-side dry run
- the production workflow applies manifests from `k8s/` instead of patching deployment structure inline
- any remaining deploy helper is thin and limited to image/secret/apply/rollout steps

## Rejected Alternatives

### Rejected: keep Docker Compose for local orchestration

Rejected because the intended local development path is host-based `uv run ...`, and maintaining Compose would preserve an unnecessary second local workflow.

### Rejected: use Kubernetes for local development too

Rejected because it adds operational weight without improving the chosen local developer experience.

### Rejected: separate service images and env contracts

Rejected because the current architecture benefits more from one shared runtime contract and one shared image, with service differences handled at the Kubernetes deployment layer.

## Success Criteria

This migration is successful when:
- developers use one root `.env.example` and host-based `uv run ...` for local work
- production uses one root Docker build and one root MicroK8s deployment path
- versioned manifests in `k8s/` define production resources
- package-local env and Docker artifacts no longer act as parallel sources of truth
- `docker-compose.yml` is removed from the supported workflow
- CI is declarative-first and no longer encodes most deployment structure inline
