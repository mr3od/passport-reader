# Extension Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Distribute the `passport-masar-extension` through the agency Telegram bot via a `/extension` command that fetches a minified ZIP from a GitHub Release asset and streams it with Arabic installation instructions and screenshots.

**Architecture:** GitHub Actions builds and publishes a minified/obfuscated `extension.zip` to a mutable `extension-latest` GitHub Release on every push to `main` that touches the extension. The agency bot fetches the ZIP at command time via the GitHub Releases API using a read-only token and streams it directly to Telegram without disk I/O. Screenshots committed as package assets guide the agency through developer-mode installation.

**Tech Stack:** `terser` (JS minification via npx), `softprops/action-gh-release` (GitHub Release management), `httpx` (async HTTP for GitHub API), `python-telegram-bot` (Telegram delivery), `Pillow` (screenshot preprocessing).

---

## File Map

**Create:**
- `scripts/build-extension.sh` — minifies JS with terser, packages `extension.zip`
- `.github/workflows/extension-ci.yml` — PR validation: build + verify ZIP, no publish
- `.github/workflows/extension-release.yml` — push to main: build + publish to `extension-latest` release
- `passport-telegram/src/passport_telegram/extension.py` — async GitHub Releases fetcher, `ExtensionFetchError`
- `passport-telegram/src/passport_telegram/assets/extension/step1.png` — processed screenshot: enable Dev Mode
- `passport-telegram/src/passport_telegram/assets/extension/step2.png` — processed screenshot: Load Unpacked (blurred)
- `passport-telegram/src/passport_telegram/assets/extension/step3.png` — processed screenshot: extension installed
- `passport-telegram/tests/test_extension_fetcher.py` — fetcher unit tests
- `passport-telegram/tests/test_extension_command.py` — command handler + config tests

**Modify:**
- `passport-telegram/src/passport_telegram/config.py` — add `github_release_read_token`, `github_repo`
- `passport-telegram/src/passport_telegram/messages.py` — add extension messages, update help/welcome
- `passport-telegram/src/passport_telegram/bot.py` — add `extension_command`, register handler
- `passport-telegram/pyproject.toml` — add `httpx>=0.27.0`, bump version to `0.3.0`
- `passport-telegram/AGENTS.md` — add `/extension` to command scope
- `passport-telegram/README.md` — document new command and env vars
- `.env.example` — add `PASSPORT_TELEGRAM_GITHUB_RELEASE_READ_TOKEN` and `PASSPORT_TELEGRAM_GITHUB_REPO`
- `docs/BACKLOG.md` — add extension distribution as completed item
- `docs/HISTORY.md` — append session entry

---

## Task 1: Build Script

**Files:**
- Create: `scripts/build-extension.sh`

- [ ] **Step 1: Write the build script**

```bash
#!/usr/bin/env bash
# Build and package the passport-masar-extension for distribution.
# Minifies JS with terser (via npx), copies static files, outputs extension.zip.
#
# Usage:
#   ./scripts/build-extension.sh
#
# Output:
#   passport-masar-extension/dist/extension.zip

set -euo pipefail

command -v npx >/dev/null 2>&1 || { echo "ERROR: npx not found — install Node.js first"; exit 1; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXTENSION_DIR="$REPO_ROOT/passport-masar-extension"
DIST_DIR="$EXTENSION_DIR/dist"
BUILD_DIR="$(mktemp -d)"

cleanup() { rm -rf "$BUILD_DIR"; }
trap cleanup EXIT

echo "Building extension from $EXTENSION_DIR"

# Minify and obfuscate JS files
JS_FILES=("background.js" "popup.js" "strings.js" "content-main.js" "content-relay.js" "config.js")
for js in "${JS_FILES[@]}"; do
    echo "  Minifying $js"
    npx --yes terser@5 "$EXTENSION_DIR/$js" \
        --compress drop_console=true \
        --mangle \
        --output "$BUILD_DIR/$js"
done

# Copy static files verbatim
cp "$EXTENSION_DIR/manifest.json" "$BUILD_DIR/"
cp "$EXTENSION_DIR/popup.html"    "$BUILD_DIR/"
cp "$EXTENSION_DIR/popup.css"     "$BUILD_DIR/"
cp -r "$EXTENSION_DIR/icons"      "$BUILD_DIR/"

# Package
mkdir -p "$DIST_DIR"
(cd "$BUILD_DIR" && zip -r - .) > "$DIST_DIR/extension.zip"

SIZE=$(wc -c < "$DIST_DIR/extension.zip")
echo "Built: $DIST_DIR/extension.zip ($SIZE bytes)"
```

- [ ] **Step 2: Make the script executable**

```bash
chmod +x scripts/build-extension.sh
```

- [ ] **Step 3: Run the script to verify it builds a non-empty ZIP**

```bash
./scripts/build-extension.sh
ls -lh passport-masar-extension/dist/extension.zip
```

Expected: file exists, size > 0 (typically 15–40 KB).

- [ ] **Step 4: Confirm the dist directory is ignored by git**

```bash
git status passport-masar-extension/dist/
```

Expected: nothing printed (root `.gitignore` already has `dist/` which covers all `dist/` subdirectories).

- [ ] **Step 5: Commit**

```bash
git add scripts/build-extension.sh
git commit -m "feat(extension): add build script for minified extension packaging [claude]"
```

---

## Task 2: Extension CI Workflow (PR Validation)

**Files:**
- Create: `.github/workflows/extension-ci.yml`

- [ ] **Step 1: Write the CI workflow**

```yaml
name: Extension CI

on:
  pull_request:
    branches:
      - main
      - production
    paths:
      - "passport-masar-extension/**"
      - "scripts/build-extension.sh"
      - ".github/workflows/extension-ci.yml"

jobs:
  build-extension:
    name: Build and Validate Extension ZIP
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Build extension
        run: bash scripts/build-extension.sh

      - name: Verify ZIP is non-empty
        run: |
          ZIP=passport-masar-extension/dist/extension.zip
          if [ ! -f "$ZIP" ]; then
            echo "ERROR: $ZIP was not created"
            exit 1
          fi
          SIZE=$(wc -c < "$ZIP")
          echo "extension.zip size: $SIZE bytes"
          if [ "$SIZE" -lt 1024 ]; then
            echo "ERROR: ZIP is suspiciously small ($SIZE bytes)"
            exit 1
          fi

      - name: Verify manifest.json is inside ZIP
        run: |
          unzip -l passport-masar-extension/dist/extension.zip | grep manifest.json
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/extension-ci.yml
git commit -m "ci(extension): validate extension build on PRs [claude]"
```

---

## Task 3: Extension Release Workflow (Publish)

**Files:**
- Create: `.github/workflows/extension-release.yml`

- [ ] **Step 1: Write the release workflow**

```yaml
name: Extension Release

on:
  push:
    branches:
      - main
    paths:
      - "passport-masar-extension/**"
      - "scripts/build-extension.sh"

jobs:
  release-extension:
    name: Build and Publish Extension to extension-latest
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Build extension
        run: bash scripts/build-extension.sh

      - name: Create or update extension-latest release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: extension-latest
          name: "Extension (latest)"
          prerelease: true
          make_latest: false
          overwrite: true
          body: |
            Auto-built from commit ${{ github.sha }}.
            Install in Chrome via Developer Mode → Load unpacked.
          files: passport-masar-extension/dist/extension.zip
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/extension-release.yml
git commit -m "ci(extension): publish minified extension to extension-latest release on merge [claude]"
```

---

## Task 4: Process and Store Installation Screenshots

**Files:**
- Create: `passport-telegram/src/passport_telegram/assets/extension/step1.png`
- Create: `passport-telegram/src/passport_telegram/assets/extension/step2.png` (blurred)
- Create: `passport-telegram/src/passport_telegram/assets/extension/step3.png`

The 3 screenshots the user provided show:
- `step1`: `chrome://extensions` page with the Developer Mode toggle visible (top-right, enabled)
- `step2`: "Load unpacked" file-picker dialog — contains internal folder names that must be blurred
- `step3`: Extension installed and showing as "Passport Masar Submitter 1.0.0" in the list

- [ ] **Step 1: Install Pillow if not available**

```bash
uv pip install pillow
```

- [ ] **Step 2: Write the screenshot processing script**

Create `scripts/process-screenshots.py`:

```python
#!/usr/bin/env python3
"""
Processes the 3 installation screenshots for the /extension command.
Blurs the file listing area in step2 to redact internal folder names.

Usage:
    python scripts/process-screenshots.py \
        --step1 /path/to/screenshot1.png \
        --step2 /path/to/screenshot2.png \
        --step3 /path/to/screenshot3.png \
        --out passport-telegram/src/passport_telegram/assets/extension/
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def blur_region(img: Image.Image, box: tuple[int, int, int, int], radius: int = 20) -> Image.Image:
    """Blur a rectangular region of the image in-place."""
    region = img.crop(box)
    blurred = region.filter(ImageFilter.GaussianBlur(radius=radius))
    img.paste(blurred, box)
    return img


def process(src: Path, dst: Path, blur_boxes: list[tuple[int, int, int, int]]) -> None:
    with Image.open(src) as img:
        # Pillow opens Retina screenshots at full 2x pixel dimensions.
        # If the image is exactly 2x the expected display size, scale boxes.
        w, h = img.size
        scale = 2 if w > 2000 else 1
        for box in blur_boxes:
            scaled = tuple(v * scale for v in box)
            blur_region(img, scaled)
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, format="PNG", optimize=True)
        print(f"Saved {dst} ({w}x{h}px, scale={scale}x)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step1", required=True)
    parser.add_argument("--step2", required=True)
    parser.add_argument("--step3", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out = Path(args.out)

    # step1: chrome://extensions page with Dev Mode toggle — no sensitive data
    process(Path(args.step1), out / "step1.png", blur_boxes=[])

    # step2: file-picker dialog — blur the entire file listing content area
    # NOTE: These coordinates were calibrated for the specific screenshots taken
    # on 2026-03-28. If re-running with different screenshots, re-calibrate by
    # opening the source image at 1x and measuring the region to redact.
    # Coordinates are at 1x display pixels; the script scales for Retina 2x.
    # Adjust if the output looks off: (left, top, right, bottom)
    # Covers: breadcrumb path ("passport-reader") + all folder name rows
    process(
        Path(args.step2),
        out / "step2.png",
        blur_boxes=[
            (400, 255, 815, 275),   # breadcrumb path bar ("passport-reader")
            (400, 285, 1065, 565),  # file listing rows (folder names + metadata)
        ],
    )

    # step3: extension installed — no sensitive data
    process(Path(args.step3), out / "step3.png", blur_boxes=[])


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the script with the screenshots from the user**

Replace the paths below with the actual paths where the user's screenshots are located:

```bash
python scripts/process-screenshots.py \
  --step1 "/var/folders/vw/b3dczfmj0bj6ysvrqdxdjmgh0000gn/T/TemporaryItems/NSIRD_screencaptureui_tyHMGw/Screenshot 2026-03-28 at 23.04.22.png" \
  --step2 "/var/folders/vw/b3dczfmj0bj6ysvrqdxdjmgh0000gn/T/TemporaryItems/NSIRD_screencaptureui_j5coR9/Screenshot 2026-03-28 at 23.04.44.png" \
  --step3 "/var/folders/vw/b3dczfmj0bj6ysvrqdxdjmgh0000gn/T/TemporaryItems/NSIRD_screencaptureui_xP1tXZ/Screenshot 2026-03-28 at 23.05.00.png" \
  --out passport-telegram/src/passport_telegram/assets/extension/
```

Expected output: 3 PNG files written, each reporting pixel dimensions and scale factor.

- [ ] **Step 4: Visually verify the output**

Open `passport-telegram/src/passport_telegram/assets/extension/step2.png` and confirm:
- The folder listing area is blurred
- "Load unpacked" button, dialog title, Cancel/Select buttons are still visible
- No internal folder names are readable

If the blur region is wrong, adjust `blur_boxes` in the script and re-run.

- [ ] **Step 5: Commit**

```bash
git add scripts/process-screenshots.py \
       passport-telegram/src/passport_telegram/assets/
git commit -m "feat(extension): add processed installation screenshots as bot assets [claude]"
```

---

## Task 5: Config — Add GitHub Settings to TelegramSettings

**Files:**
- Modify: `passport-telegram/src/passport_telegram/config.py`
- Modify: `.env.example`
- Test: `passport-telegram/tests/test_telegram_config.py`

- [ ] **Step 1: Write the failing tests**

Add to `passport-telegram/tests/test_telegram_config.py`:

```python
def test_telegram_settings_github_release_token_defaults_to_none():
    settings = TelegramSettings.model_construct(bot_token=SecretStr("token"))
    assert settings.github_release_read_token is None


def test_telegram_settings_github_repo_defaults_to_none():
    settings = TelegramSettings.model_construct(bot_token=SecretStr("token"))
    assert settings.github_repo is None


def test_telegram_settings_github_release_token_is_secret():
    settings = TelegramSettings.model_construct(
        bot_token=SecretStr("token"),
        github_release_read_token=SecretStr("ghp_secret123"),
    )
    assert "ghp_secret123" not in str(settings)
    assert settings.github_release_read_token.get_secret_value() == "ghp_secret123"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest passport-telegram/tests/test_telegram_config.py -q
```

Expected: 3 failures — `TelegramSettings` has no `github_release_read_token` or `github_repo` fields.

- [ ] **Step 3: Update TelegramSettings**

Full updated `passport-telegram/src/passport_telegram/config.py`:

```python
from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PASSPORT_TELEGRAM_",
        env_file=".env",
        extra="ignore",
    )

    bot_token: SecretStr
    album_collection_window_seconds: float = 1.5
    max_images_per_batch: int = 10
    log_level: str = "INFO"
    github_release_read_token: SecretStr | None = None
    github_repo: str | None = None
```

- [ ] **Step 4: Run tests — must pass**

```bash
uv run pytest passport-telegram/tests/test_telegram_config.py -q
```

Expected: all pass.

- [ ] **Step 5: Update `.env.example`**

Add after the `PASSPORT_TELEGRAM_LOG_LEVEL` line:

```
PASSPORT_TELEGRAM_GITHUB_RELEASE_READ_TOKEN=
PASSPORT_TELEGRAM_GITHUB_REPO=owner/passport-reader
```

- [ ] **Step 6: Commit**

```bash
git add passport-telegram/src/passport_telegram/config.py \
       passport-telegram/tests/test_telegram_config.py \
       .env.example
git commit -m "feat(telegram): add github_release_read_token and github_repo settings [claude]"
```

---

## Task 6: Extension Fetcher Module

**Files:**
- Create: `passport-telegram/src/passport_telegram/extension.py`
- Modify: `passport-telegram/pyproject.toml` (add `httpx>=0.27.0`)
- Test: `passport-telegram/tests/test_extension_fetcher.py`

- [ ] **Step 1: Add httpx dependency**

In `passport-telegram/pyproject.toml`, add `httpx>=0.27.0` to the `dependencies` list:

```toml
dependencies = [
  "httpx>=0.27.0",
  "passport-platform",
  "pydantic-settings>=2.4.0",
  "python-dotenv>=1.0.1",
  "python-telegram-bot[job-queue]>=21.6",
]
```

Then sync:

```bash
uv sync --all-packages
```

- [ ] **Step 2: Write the failing tests**

Create `passport-telegram/tests/test_extension_fetcher.py`:

```python
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import passport_telegram.extension as ext_module
from passport_telegram.extension import ExtensionFetchError, fetch_extension_zip

_ASSET_URL = "https://api.github.com/repos/test/repo/releases/assets/999"
_ZIP_MAGIC = b"PK\x03\x04"


@pytest.fixture(autouse=True)
def clear_zip_cache():
    """Isolate the module-level TTL cache between tests."""
    ext_module._clear_cache()
    yield
    ext_module._clear_cache()


def _make_mock_client(
    *,
    release_status: int,
    release_body: dict,
    asset_status: int = 200,
    asset_content: bytes = _ZIP_MAGIC,
) -> AsyncMock:
    """Build a fake httpx.AsyncClient for the two-request fetch flow."""
    release_resp = MagicMock()
    release_resp.status_code = release_status
    release_resp.json.return_value = release_body

    asset_resp = MagicMock()
    asset_resp.status_code = asset_status
    asset_resp.content = asset_content

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[release_resp, asset_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def test_fetch_extension_zip_returns_bytes_on_success():
    body = {"assets": [{"name": "extension.zip", "url": _ASSET_URL}]}
    mock_client = _make_mock_client(release_status=200, release_body=body)

    with patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client):
        result = asyncio.run(fetch_extension_zip(token="ghp_test", repo="test/repo"))

    assert result == _ZIP_MAGIC


def test_fetch_extension_zip_raises_on_404_release():
    mock_client = _make_mock_client(release_status=404, release_body={"message": "Not Found"})

    with patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ExtensionFetchError, match="release not found"):
            asyncio.run(fetch_extension_zip(token="ghp_test", repo="test/repo"))


def test_fetch_extension_zip_raises_on_api_error():
    mock_client = _make_mock_client(release_status=500, release_body={})

    with patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ExtensionFetchError, match="GitHub API error"):
            asyncio.run(fetch_extension_zip(token="ghp_test", repo="test/repo"))


def test_fetch_extension_zip_raises_when_zip_asset_missing():
    body = {"assets": [{"name": "other-file.zip", "url": _ASSET_URL}]}
    mock_client = _make_mock_client(release_status=200, release_body=body)

    with patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ExtensionFetchError, match="extension.zip not found"):
            asyncio.run(fetch_extension_zip(token="ghp_test", repo="test/repo"))


def test_fetch_extension_zip_raises_on_asset_download_failure():
    body = {"assets": [{"name": "extension.zip", "url": _ASSET_URL}]}
    mock_client = _make_mock_client(
        release_status=200,
        release_body=body,
        asset_status=403,
        asset_content=b"",
    )

    with patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ExtensionFetchError, match="asset download failed"):
            asyncio.run(fetch_extension_zip(token="ghp_test", repo="test/repo"))


def test_fetch_extension_zip_raises_when_asset_exceeds_size_limit():
    body = {"assets": [{"name": "extension.zip", "url": _ASSET_URL}]}
    mock_client = _make_mock_client(
        release_status=200,
        release_body=body,
        asset_content=b"x" * (5_000_001),
    )

    with patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ExtensionFetchError, match="asset too large"):
            asyncio.run(fetch_extension_zip(token="ghp_test", repo="test/repo"))
```

- [ ] **Step 3: Run to confirm all fail**

```bash
uv run pytest passport-telegram/tests/test_extension_fetcher.py -q
```

Expected: 6 failures — `passport_telegram.extension` does not exist.

- [ ] **Step 4: Create `extension.py`**

Create `passport-telegram/src/passport_telegram/extension.py`:

```python
from __future__ import annotations

import time

import httpx

_CACHE_TTL = 300.0  # seconds — re-fetch after 5 minutes
_zip_cache: tuple[float, bytes] | None = None  # (timestamp, zip_bytes)

_MAX_ZIP_BYTES = 5_000_000  # 5 MB sanity limit


class ExtensionFetchError(Exception):
    """Raised when the extension ZIP cannot be fetched from GitHub Releases."""


def _clear_cache() -> None:
    """Reset the in-memory ZIP cache. Exposed for use in tests only."""
    global _zip_cache
    _zip_cache = None


async def fetch_extension_zip(*, token: str, repo: str) -> bytes:
    """Fetch the latest extension ZIP from the ``extension-latest`` GitHub Release.

    Results are cached in-process for ``_CACHE_TTL`` seconds to avoid redundant
    API calls when multiple agencies run ``/extension`` in quick succession.

    Makes two requests on a cache miss: one to resolve the asset URL from the
    release metadata, one to download the ZIP bytes.

    Args:
        token: A GitHub fine-grained personal access token with read access to
               repository contents and releases.
        repo: Full repository name in ``owner/repo`` form.

    Raises:
        ExtensionFetchError: If the release, asset, or download cannot be completed.
    """
    global _zip_cache
    now = time.monotonic()
    if _zip_cache is not None:
        ts, data = _zip_cache
        if now - ts < _CACHE_TTL:
            return data

    base_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(headers=base_headers, timeout=30.0) as client:
        release_url = f"https://api.github.com/repos/{repo}/releases/tags/extension-latest"
        resp = await client.get(release_url)

        if resp.status_code == 404:
            raise ExtensionFetchError("extension release not found")
        if resp.status_code != 200:
            raise ExtensionFetchError(f"GitHub API error: {resp.status_code}")

        assets = resp.json().get("assets", [])
        asset = next((a for a in assets if a["name"] == "extension.zip"), None)
        if asset is None:
            raise ExtensionFetchError("extension.zip not found in release assets")

        # Use only Accept override at request level; Authorization is inherited
        # from the client-level headers via httpx merge semantics.
        download_resp = await client.get(
            asset["url"],
            headers={"Accept": "application/octet-stream"},
            follow_redirects=True,
        )
        if download_resp.status_code != 200:
            raise ExtensionFetchError(f"asset download failed: {download_resp.status_code}")

        data = download_resp.content
        if len(data) > _MAX_ZIP_BYTES:
            raise ExtensionFetchError(f"asset too large: {len(data)} bytes")

        _zip_cache = (now, data)
        return data
```

- [ ] **Step 5: Run tests — must all pass**

```bash
uv run pytest passport-telegram/tests/test_extension_fetcher.py -q
```

Expected: 6 passed.

- [ ] **Step 6: Lint and type-check**

```bash
uv run ruff check passport-telegram/src
uv run ruff format passport-telegram/src
uv run ty check passport-telegram/src
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add passport-telegram/src/passport_telegram/extension.py \
       passport-telegram/tests/test_extension_fetcher.py \
       passport-telegram/pyproject.toml \
       uv.lock
git commit -m "feat(telegram): add GitHub Releases fetcher for extension distribution [claude]"
```

---

## Task 7: Arabic Messages for Extension Command

**Files:**
- Modify: `passport-telegram/src/passport_telegram/messages.py`
- Test: `passport-telegram/tests/test_messages.py`

- [ ] **Step 1: Write the failing tests**

Read `passport-telegram/tests/test_messages.py`, then add:

```python
from passport_telegram.messages import (
    extension_fetch_error_text,
    extension_installing_text,
    extension_step1_caption,
    extension_step2_caption,
    extension_step3_caption,
)


def test_extension_installing_text_is_arabic_and_covers_all_steps():
    text = extension_installing_text()
    assert "chrome://extensions" in text
    assert "Load unpacked" in text
    assert "/token" in text
    # Must be Arabic (contains Arabic characters)
    assert any("\u0600" <= c <= "\u06ff" for c in text)


def test_extension_step_captions_are_arabic():
    for fn in (extension_step1_caption, extension_step2_caption, extension_step3_caption):
        text = fn()
        assert any("\u0600" <= c <= "\u06ff" for c in text)


def test_extension_fetch_error_text_is_arabic():
    text = extension_fetch_error_text()
    assert any("\u0600" <= c <= "\u06ff" for c in text)


def test_welcome_text_includes_extension_command():
    from passport_telegram.messages import welcome_text
    assert "/extension" in welcome_text()


def test_help_text_includes_extension_command():
    from passport_telegram.messages import help_text
    assert "/extension" in help_text()
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest passport-telegram/tests/test_messages.py -q
```

Expected: failures on the new tests.

- [ ] **Step 3: Add extension messages and update welcome/help in `messages.py`**

Add these functions to the end of `messages.py`:

```python
def extension_installing_text() -> str:
    """Step-by-step Arabic guide for installing the extension in Chrome developer mode."""
    return (
        "خطوات تثبيت إضافة مسار:\n\n"
        "1️⃣ افتح متصفح كروم وانتقل إلى:\n"
        "chrome://extensions\n\n"
        "2️⃣ فعّل وضع المطور (Developer Mode) من الزاوية اليمنى العليا.\n"
        "ثم اضغط Load unpacked واختر المجلد الذي فككت فيه ضغط الملف.\n\n"
        "3️⃣ ستظهر إضافة Passport Masar Submitter في القائمة.\n\n"
        "سجّل دخولك بأمر /token وأدخل الرمز داخل الإضافة."
    )


def extension_step1_caption() -> str:
    """Caption for the first installation screenshot."""
    return "الخطوة 1: افتح chrome://extensions وفعّل وضع المطور من الزاوية اليمنى العليا"


def extension_step2_caption() -> str:
    """Caption for the second installation screenshot."""
    return "الخطوة 2: اضغط Load unpacked واختر مجلد الإضافة بعد فك الضغط"


def extension_step3_caption() -> str:
    """Caption for the third installation screenshot."""
    return "الخطوة 3: ظهرت الإضافة بنجاح — سجّل دخولك الآن بأمر /token"


def extension_fetch_error_text() -> str:
    """Shown when the extension ZIP cannot be fetched from GitHub Releases."""
    return f"تعذر تحميل ملف الإضافة في الوقت الحالي. حاول مرة أخرى لاحقًا. {SUPPORT_CONTACT_TEXT}"
```

Update `welcome_text()` — add `/extension` to the commands list:

```python
def welcome_text() -> str:
    return (
        "أهلًا بك في بوت رفع وتدقيق الجوازات.\n\n"
        "أرسل صورة جواز واحدة أو عدة صور، وسأقوم بالتحقق من الجواز "
        "واستخراج البيانات لكل صورة بشكل مستقل.\n\n"
        "أوامر المستخدم:\n"
        "/account - عرض الخطة والاستخدام الحالي\n"
        "/usage - عرض تفاصيل الاستخدام الشهري\n"
        "/plan - عرض الخطة الحالية وحالة الحساب\n"
        "/token - إصدار رمز مؤقت لتسجيل الدخول في الإضافة\n"
        "/extension - تحميل إضافة مسار وتعليمات التثبيت\n"
        "/masar - عرض الجوازات المعلقة أو الفاشلة في مسار\n\n"
        f"{SUPPORT_CONTACT_TEXT}"
    )
```

Update `help_text()` — add `/extension` to the commands list:

```python
def help_text() -> str:
    return (
        "طريقة الاستخدام:\n"
        "1. أرسل صورة الجواز كصورة أو كملف.\n"
        "2. تأكد من أن الصورة واضحة وتُظهر كامل صفحة الجواز.\n"
        "3. يمكنك إرسال أكثر من صورة في دفعة واحدة.\n"
        "4. ستصلك النتيجة لكل صورة بشكل مستقل، مع البيانات المستخرجة.\n\n"
        "أوامر المستخدم:\n"
        "/account - عرض الخطة والاستخدام الحالي\n"
        "/usage - عرض تفاصيل الاستخدام الشهري\n"
        "/plan - عرض الخطة الحالية وحالة الحساب\n"
        "/token - إصدار رمز مؤقت لتسجيل الدخول في الإضافة\n"
        "/extension - تحميل إضافة مسار وتعليمات التثبيت\n"
        "/masar - عرض الجوازات المعلقة أو الفاشلة في مسار\n\n"
        "الملفات المدعومة: JPG, JPEG, PNG, WEBP, TIF, TIFF\n\n"
        f"{SUPPORT_CONTACT_TEXT}"
    )
```

- [ ] **Step 4: Run tests — must all pass**

```bash
uv run pytest passport-telegram/tests/test_messages.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add passport-telegram/src/passport_telegram/messages.py \
       passport-telegram/tests/test_messages.py
git commit -m "feat(telegram): add Arabic extension messages and update help/welcome [claude]"
```

---

## Task 8: extension_command Handler

**Files:**
- Modify: `passport-telegram/src/passport_telegram/bot.py`
- Test: `passport-telegram/tests/test_extension_command.py`

- [ ] **Step 1: Write the failing tests**

Create `passport-telegram/tests/test_extension_command.py`:

```python
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from passport_platform.enums import UserStatus
from pydantic import SecretStr
from telegram.ext import CommandHandler, ContextTypes

from passport_telegram.bot import extension_command
from passport_telegram.config import TelegramSettings
from passport_telegram.extension import ExtensionFetchError


class FakeExtensionBot:
    """Minimal bot fake that records document and reply_text calls."""

    def __init__(self) -> None:
        self.documents: list[dict] = []
        self.photos: list[dict] = []

    async def send_document(self, *, chat_id: int, document, filename: str, caption: str = "") -> None:
        content = document.read() if hasattr(document, "read") else document
        self.documents.append({"chat_id": chat_id, "content": content, "filename": filename})

    async def send_photo(self, *, chat_id: int, photo: bytes, caption: str = "") -> None:
        self.photos.append({"chat_id": chat_id, "caption": caption})


class FakeReplyMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


def _make_settings(*, with_token: bool = True) -> TelegramSettings:
    return TelegramSettings.model_construct(
        bot_token=SecretStr("test-bot-token"),
        github_release_read_token=SecretStr("ghp_test") if with_token else None,
        github_repo="test/repo" if with_token else None,
    )


def _make_services(*, blocked: bool = False) -> object:
    return SimpleNamespace(
        users=SimpleNamespace(
            get_or_create_user=lambda cmd: SimpleNamespace(
                id=1,
                external_user_id="12345",
                status=UserStatus.BLOCKED if blocked else UserStatus.ACTIVE,
            )
        )
    )


def _make_context(
    *, settings: TelegramSettings, services: object, bot: FakeExtensionBot
) -> ContextTypes.DEFAULT_TYPE:
    return cast(
        ContextTypes.DEFAULT_TYPE,
        SimpleNamespace(
            application=SimpleNamespace(bot_data={"settings": settings, "services": services}),
            bot=bot,
        ),
    )


def _make_update(reply: FakeReplyMessage, chat_id: int = 42) -> object:
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=SimpleNamespace(id=999, first_name="Agency", last_name=None, username=None),
        effective_message=reply,
    )


def test_extension_command_sends_zip_on_success():
    bot = FakeExtensionBot()
    reply = FakeReplyMessage()
    settings = _make_settings(with_token=True)
    context = _make_context(settings=settings, services=_make_services(), bot=bot)
    update = _make_update(reply)
    zip_bytes = b"PK\x03\x04fake-zip-content"

    with patch("passport_telegram.bot.fetch_extension_zip", new=AsyncMock(return_value=zip_bytes)):
        asyncio.run(extension_command(update, context))

    assert len(bot.documents) == 1
    assert bot.documents[0]["content"] == zip_bytes
    assert bot.documents[0]["filename"] == "passport-masar-extension.zip"
    assert len(reply.replies) == 1  # instruction text


def test_extension_command_sends_arabic_error_on_fetch_failure():
    bot = FakeExtensionBot()
    reply = FakeReplyMessage()
    settings = _make_settings(with_token=True)
    context = _make_context(settings=settings, services=_make_services(), bot=bot)
    update = _make_update(reply)

    with patch(
        "passport_telegram.bot.fetch_extension_zip",
        new=AsyncMock(side_effect=ExtensionFetchError("release not found")),
    ):
        asyncio.run(extension_command(update, context))

    assert len(bot.documents) == 0
    assert len(reply.replies) == 1
    assert any("\u0600" <= c <= "\u06ff" for c in reply.replies[0])


def test_extension_command_sends_error_when_token_not_configured():
    bot = FakeExtensionBot()
    reply = FakeReplyMessage()
    settings = _make_settings(with_token=False)
    context = _make_context(settings=settings, services=_make_services(), bot=bot)
    update = _make_update(reply)

    asyncio.run(extension_command(update, context))

    assert len(bot.documents) == 0
    assert len(reply.replies) == 1
    assert any("\u0600" <= c <= "\u06ff" for c in reply.replies[0])


def test_extension_command_blocks_blocked_user():
    bot = FakeExtensionBot()
    reply = FakeReplyMessage()
    settings = _make_settings(with_token=True)
    context = _make_context(settings=settings, services=_make_services(blocked=True), bot=bot)
    update = _make_update(reply)

    with patch("passport_telegram.bot.fetch_extension_zip", new=AsyncMock(return_value=b"zip")):
        asyncio.run(extension_command(update, context))

    assert len(bot.documents) == 0
    assert len(reply.replies) == 1
    assert any("\u0600" <= c <= "\u06ff" for c in reply.replies[0])


def test_extension_command_handler_is_configured():
    """Verify extension_command is importable and maps to the 'extension' command name."""
    handler = CommandHandler("extension", extension_command)
    assert "extension" in handler.commands
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest passport-telegram/tests/test_extension_command.py -q
```

Expected: failures — `extension_command` does not exist yet.

- [ ] **Step 3: Add the handler to `bot.py`**

Add these imports at the top of `bot.py` (with the existing imports):

```python
import io
```

Add to the `from passport_telegram.messages import (...)` block:

```python
    extension_fetch_error_text,
    extension_installing_text,
    extension_step1_caption,
    extension_step2_caption,
    extension_step3_caption,
```

Add the import for the fetcher after the existing `from passport_telegram.` imports:

```python
from passport_telegram.extension import ExtensionFetchError, fetch_extension_zip
```

Add the constant and handler function after the `masar_command` function:

```python
_EXTENSION_ASSETS_DIR = Path(__file__).parent / "assets" / "extension"
_EXTENSION_STEPS = [
    ("step1.png", extension_step1_caption),
    ("step2.png", extension_step2_caption),
    ("step3.png", extension_step3_caption),
]


async def extension_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the latest extension ZIP and Arabic installation instructions to the agency.

    Checks user registration and blocked status before delivering the ZIP,
    consistent with other self-service commands.
    """
    settings: TelegramSettings = context.application.bot_data["settings"]
    services: BotServices = context.application.bot_data["services"]

    user = await _get_or_create_user(update, services)
    if user.status is UserStatus.BLOCKED:
        await _reply_text(update, user_blocked_text())
        return

    if settings.github_release_read_token is None or settings.github_repo is None:
        await _reply_text(update, extension_fetch_error_text())
        return

    chat = update.effective_chat
    if chat is None:
        return

    try:
        zip_bytes = await fetch_extension_zip(
            token=settings.github_release_read_token.get_secret_value(),
            repo=settings.github_repo,
        )
    except ExtensionFetchError:
        logging.getLogger(__name__).exception("extension_fetch_failed")
        await _reply_text(update, extension_fetch_error_text())
        return

    await _reply_text(update, extension_installing_text())

    for filename, caption_fn in _EXTENSION_STEPS:
        screenshot = _EXTENSION_ASSETS_DIR / filename
        if screenshot.exists():
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=screenshot.read_bytes(),
                caption=caption_fn(),
            )

    await context.bot.send_document(
        chat_id=chat.id,
        document=io.BytesIO(zip_bytes),
        filename="passport-masar-extension.zip",
        caption="ملف الإضافة — قم بتحميله وفك ضغطه",
    )
```

Note: `Path` is already imported in `bot.py` (line 7: `from pathlib import Path`). No new import needed for that. The `io` import is new and must be added.

Register the handler inside `build_application`, after `application.add_handler(CommandHandler("masar", masar_command))`:

```python
    application.add_handler(CommandHandler("extension", extension_command))
```

- [ ] **Step 4: Run tests — must all pass**

```bash
uv run pytest passport-telegram/tests/test_extension_command.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest passport-telegram/tests/ -q
```

Expected: all pass.

- [ ] **Step 6: Lint and type-check**

```bash
uv run ruff check passport-telegram/src
uv run ruff format passport-telegram/src
uv run ty check passport-telegram/src
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add passport-telegram/src/passport_telegram/bot.py \
       passport-telegram/tests/test_extension_command.py
git commit -m "feat(telegram): add /extension command with GitHub Releases fetch and screenshots [claude]"
```

---

## Task 9: Documentation, Metadata, and Version Bump

**Files:**
- Modify: `passport-telegram/pyproject.toml` (version)
- Modify: `passport-telegram/AGENTS.md`
- Modify: `passport-telegram/README.md`
- Modify: `docs/BACKLOG.md`
- Modify: `docs/HISTORY.md`

- [ ] **Step 1: Bump version in `passport-telegram/pyproject.toml`**

Change `version = "0.2.0"` to `version = "0.3.0"`.

- [ ] **Step 2: Update `passport-telegram/AGENTS.md`**

Replace the Command scope section:

```markdown
## Command scope

- Self-service agency commands only: `/start`, `/help`, `/account`, `/usage`, `/plan`, `/token`, `/masar`, `/extension`
- No admin/operator commands
- No cross-user lookups
- `/usage` is self-only and must not support argument-based lookups
- `/extension` fetches the latest extension ZIP from GitHub Releases at runtime using
  `PASSPORT_TELEGRAM_GITHUB_RELEASE_READ_TOKEN` and `PASSPORT_TELEGRAM_GITHUB_REPO`;
  if either is unset, it returns an Arabic error message
```

- [ ] **Step 3: Update `passport-telegram/README.md`**

Add a new section after the existing command documentation (before `## Setup` or at the end of commands section):

```markdown
## /extension command

Agencies run `/extension` to receive the latest Chrome extension ZIP and
step-by-step Arabic installation instructions with screenshots.

The ZIP is fetched at runtime from a GitHub Release tagged `extension-latest`.
Two env vars are required:

| Variable | Description |
|---|---|
| `PASSPORT_TELEGRAM_GITHUB_RELEASE_READ_TOKEN` | Fine-grained PAT with read access to repo contents and releases |
| `PASSPORT_TELEGRAM_GITHUB_REPO` | Repository in `owner/repo` form (e.g. `myorg/passport-reader`) |

If either var is absent, `/extension` returns an Arabic unavailability message.

The extension is built and published to the `extension-latest` release automatically
by `.github/workflows/extension-release.yml` on every push to `main` that touches
`passport-masar-extension/`.
```

- [ ] **Step 4: Update `docs/BACKLOG.md`**

Add this block in the **Highest Priority Work** section (or a new **Extension Distribution** section), marked as completed:

```markdown
### E1. Extension distribution via agency bot

Status
- Completed by `claude`
- `/extension` command added to `passport-telegram`; minified ZIP published via GitHub Releases

**Goal**
- Agencies install the extension through the bot, not via manual file transfer

**What was built**
- `scripts/build-extension.sh` — terser-based minification + ZIP packaging
- `.github/workflows/extension-ci.yml` — build validation on PRs
- `.github/workflows/extension-release.yml` — publish to `extension-latest` on merge
- `passport-telegram/src/passport_telegram/extension.py` — async GitHub Releases fetcher
- `/extension` Telegram command with Arabic instructions + screenshots + ZIP delivery
```

- [ ] **Step 5: Append to `docs/HISTORY.md`**

Append:

```markdown
## 2026-03-28 — Extension distribution via agency bot [claude]

Added `/extension` command to `passport-telegram` (v0.3.0). Agencies receive
the minified extension ZIP and step-by-step Arabic installation guide directly
through the bot. GitHub Actions CI validates builds on PRs and publishes to the
`extension-latest` GitHub Release on merge to main. The bot fetches the ZIP at
runtime via the GitHub Releases API using `PASSPORT_TELEGRAM_GITHUB_RELEASE_READ_TOKEN`.
```

- [ ] **Step 6: Commit all documentation**

```bash
git add passport-telegram/pyproject.toml \
       passport-telegram/AGENTS.md \
       passport-telegram/README.md \
       docs/BACKLOG.md \
       docs/HISTORY.md
git commit -m "docs(telegram): update docs and bump to v0.3.0 for /extension command [claude]"
```

---

## Task 10: Final Verification

- [ ] **Step 1: Full ruff check across all touched packages**

```bash
uv run ruff check passport-telegram/src passport-core/src passport-platform/src passport-api/src passport-admin-bot/src
```

Expected: no errors.

- [ ] **Step 2: Format check**

```bash
uv run ruff format passport-telegram/src passport-core/src passport-platform/src passport-api/src passport-admin-bot/src
```

Expected: no files modified (already formatted).

- [ ] **Step 3: Type check**

```bash
uv run ty check passport-telegram/src
```

Expected: no errors.

- [ ] **Step 4: Full test suite**

```bash
uv run pytest passport-admin-bot/tests passport-core/tests passport-platform/tests passport-api/tests passport-telegram/tests passport-benchmark/tests -q
```

Expected: all pass, no regressions.

- [ ] **Step 5: Import boundary check**

```bash
uv run lint-imports
```

Expected: no violations (extension.py depends only on httpx, which is not a repo package).

- [ ] **Step 6: Verify PNG assets are included in the built wheel**

Hatchling includes all files under the package directory by default, but confirm:

```bash
uv run python -c "
import importlib.resources as r
pkg = r.files('passport_telegram') / 'assets' / 'extension'
files = list(pkg.iterdir())
print('Assets found:', [f.name for f in files])
assert any(f.name == 'step1.png' for f in files), 'step1.png missing from package'
assert any(f.name == 'step2.png' for f in files), 'step2.png missing from package'
assert any(f.name == 'step3.png' for f in files), 'step3.png missing from package'
print('OK — all screenshots present in installed package')
"
```

Expected: prints all three PNG filenames without assertion errors. If it fails, add this to `passport-telegram/pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/passport_telegram"]
artifacts = ["src/passport_telegram/assets/**"]
```

---

## Self-Review Checklist

**Spec coverage:**

| Requirement | Task |
|---|---|
| Build as GitHub Release asset, not committed artifact | Tasks 1, 2, 3 |
| CI validates on PRs before merge | Task 2 |
| Publish to mutable `extension-latest` channel | Task 3 (`overwrite: true`) |
| Agencies receive extension only via agency bot | Task 8 (user status gate) |
| `/extension` fetches ZIP from GitHub API at runtime | Task 6, 8 |
| Streams ZIP without writing to disk | Task 8 (`io.BytesIO`) |
| Sends screenshots + instructions | Task 4, 7, 8 |
| Update bot.py, messages.py, README.md, AGENTS.md, BACKLOG.md, HISTORY.md | Task 7, 8, 9 |
| All Arabic text in `messages.py` | Task 7 |
| Failure handling: missing asset / API error → Arabic text | Task 8 |
| Blocked-user gate before ZIP delivery | Task 8 |
| `GITHUB_RELEASE_READ_TOKEN` env var name | Task 5 |
| Tests: success, failure, blocked-user, registration, config, size limit, cache | Tasks 5, 6, 8 |
| Cache isolates between tests (autouse fixture) | Task 6 |
| Verify: ruff, ty, pytest, lint-imports, package assets | Task 10 |
| No committed ZIPs | dist/ already in .gitignore |
| No Docker wiring assumed | not included |
| Version bump | Task 9 |
| npx guard in build script | Task 1 |
| CI workflow self-triggers on its own changes | Task 2 |
| Asset overwrite on re-publish | Task 3 |
