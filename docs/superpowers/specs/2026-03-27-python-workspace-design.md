# Python Workspace Packaging Design

## Goal

Convert the repository into a root-managed Python workspace with shared tooling configuration while preserving the existing architecture boundaries and keeping the main packages as separate installable distributions.

## Scope

In scope:
- root workspace management through one root `pyproject.toml`
- shared repository-wide tool configuration
- thin per-package `pyproject.toml` manifests for build metadata only
- consistent root-based developer workflow
- excluding experimental packages from the main workspace when they are not maintained to the same standard

Out of scope:
- collapsing all code into a single Python distribution
- changing package boundaries defined in `AGENTS.md`
- moving code between `passport-core`, `passport-platform`, `passport-api`, `passport-telegram`, and `passport-benchmark`
- publishing or release automation changes beyond what packaging structure requires
- making `browser-session` a first-class maintained package in this migration

## Current State

The repository currently has:
- a root `pyproject.toml` with basic `uv` workspace membership and shared `ruff` settings
- per-package `pyproject.toml` files that each duplicate tool configuration and dev dependencies
- package-local virtualenv workflows in README files
- one experimental package, `browser-session`, that is not ready to participate in root workspace operations

The architecture rules require package boundaries to remain meaningful:
- `passport-core` must not depend on other repo packages
- `passport-platform` is the only package allowed to import `passport-core`
- adapters must depend on `passport-platform`, not `passport-core`

These constraints make a single merged distribution the wrong target.

## Decision

Use a root workspace plus thin per-package manifests.

### Rationale

This keeps the benefits of a monorepo workspace:
- one root lockfile
- one shared tool configuration
- one default developer entry point

While preserving the benefits of separate distributions:
- package boundaries remain explicit in metadata
- dependency direction remains encoded in packaging
- each package can still expose its own runtime dependencies and entry points

This design also accepts the main trade-off of a single workspace lockfile:
- all maintained workspace members must declare compatible dependency ranges
- a version conflict in one maintained package can block root resolution for the whole workspace

## Target Workspace Structure

Main workspace members:
- `passport-core`
- `passport-platform`
- `passport-api`
- `passport-telegram`
- `passport-benchmark`

Excluded from the main workspace:
- `browser-session`

### Why `browser-session` is excluded

`browser-session` is experimental and currently does not meet the baseline needed for stable workspace participation. It should not be allowed to break root dependency resolution, linting, or sync commands for the maintained production packages.

If it later becomes maintained, it can be added back once it has complete package metadata and passes root-level verification.

## Packaging Model

### Root `pyproject.toml`

The root file becomes the control plane for shared repository concerns:
- `tool.uv.workspace.members`
- root dependency groups for developer tooling
- shared `ruff` configuration
- shared `pytest` configuration where it is truly common
- shared `tool.ty` configuration if introduced
- root-level package exclusions or workspace defaults
- shared `tool.uv.sources` declarations for internal package resolution where appropriate

The root file should not pretend the repository is one distribution. It is a workspace manifest, not a replacement for package-level distribution metadata.

The root workspace configuration should make internal package resolution explicit so local development does not fall back to PyPI for maintained workspace packages.

### Package `pyproject.toml` files

Each maintained package keeps a minimal manifest with only:
- `[project]` identity fields: name, version, description, readme, requires-python
- runtime dependencies specific to that distribution
- package-specific entry points
- build backend declaration
- backend package target configuration
- workspace source declarations only where still required by the toolchain

Each package manifest should remove:
- duplicated `ruff` configuration
- duplicated `pytest` configuration when the root config is sufficient
- duplicated dev dependency definitions when those come from the root workspace
- any obsolete compatibility settings no longer needed after root workspace adoption

## Dependency Direction

The package dependency chain remains:
- `passport-core`: no internal repo dependencies
- `passport-platform`: depends on `passport-core`
- `passport-api`: depends on `passport-platform`
- `passport-telegram`: depends on `passport-platform`
- `passport-benchmark`: depends on `passport-core`

This must remain explicit in package metadata after the migration.

Because the workspace uses one root lockfile, these maintained packages must also keep dependency constraints mutually resolvable. The migration must include an audit for incompatible version pins and conflicting ranges.

## Developer Workflow

### Default workflow

Developers should work from the repository root by default.

Examples:
- `uv sync`
- `uv run ruff check ...`
- `uv run pytest ...`
- `uv run passport-api`
- `uv run passport-telegram`

In CI, commands that rely on the lockfile should use `--locked` so the pipeline verifies reproducibility instead of silently re-resolving dependencies.

### Package-local workflow

Package-local workflows may continue to work, but they are no longer the primary documented path. Documentation should move toward root-first commands unless there is a package-specific reason not to.

### Lockfile

The workspace should use one root `uv.lock` for maintained packages in the main workspace.

## Documentation Changes

README files should be updated to reflect:
- root-first setup and sync commands
- package-specific commands run from the root workspace when possible
- the fact that `browser-session` is experimental and outside the main workspace path

Documentation should avoid teaching conflicting package-local environment management as the default path.

## Implementation Outline

1. Adjust the root `pyproject.toml` to represent the real maintained workspace members.
2. Remove `browser-session` from workspace membership.
3. Add shared root dependency groups for tooling used across packages.
4. Define workspace-aware internal dependency resolution with `tool.uv.sources`.
5. Audit maintained package dependency constraints for conflicts that would break the single root lockfile.
6. Remove duplicated shared tool configuration from package manifests.
7. Keep only distribution metadata and package-specific dependencies in package manifests.
8. Update README files to document the root-first workflow.
9. Regenerate the root lockfile.
10. Verify sync, lint, and selected package entry points from the root.

## Risks

### Tooling assumptions

Some Python packaging tools still assume package-local metadata for separate distributions. Removing package manifests entirely would break this model. The implementation must keep thin package manifests rather than deleting them.

### CI drift

Existing CI and deployment scripts may still assume package-local commands or local manifests. Those paths need verification after the workspace changes.

### Shared lockfile conflicts

The workspace lockfile couples resolution across all maintained packages. Divergent or incompatible version requirements can prevent the root environment from resolving at all, so version constraints must be reviewed together instead of package by package.

### Experimental package contamination

If `browser-session` stays in the main workspace, it can continue breaking root operations. Excluding it is part of making the workspace reliable.

## Verification Plan

Minimum verification for this migration:
- root `uv sync` succeeds
- root `uv sync --locked` succeeds in CI-oriented verification
- root `uv run ruff check` succeeds for maintained packages
- root `uv run pytest` succeeds for at least the packages with active tests or targeted test selections
- `uv run passport-api` resolves from the root workspace
- `uv run passport-telegram` resolves from the root workspace
- building maintained distributions still works

## Non-Goals and Rejected Alternatives

### Rejected: one combined distribution

Rejected because it weakens architectural enforcement and collapses package identity that the repository explicitly relies on.

### Rejected: one root manifest with no package-local manifests

Rejected because standard Python tooling does not cleanly support multiple separate distributions from one root metadata file without custom build infrastructure.

### Rejected: keeping the current duplicated configuration

Rejected because it creates unnecessary maintenance overhead and makes the root workspace only partially authoritative.

## Success Criteria

This migration is successful when:
- maintained packages remain separate installable distributions
- root workspace commands work without package-local setup ceremony
- duplicated tooling configuration is removed from package manifests
- documentation consistently teaches the root-first workflow
- `browser-session` no longer interferes with maintained workspace operations
