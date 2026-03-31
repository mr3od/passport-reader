"""Fetch the packaged Chrome extension ZIP from GitHub Releases."""

from __future__ import annotations

import asyncio
import time
from typing import Final

import httpx

_CACHE_TTL: Final = 300.0  # 5 minutes
_MAX_ZIP_BYTES: Final = 5_000_000  # 5 MB guard

_zip_cache: tuple[float, bytes] | None = None
_fetch_lock: asyncio.Lock = asyncio.Lock()


class ExtensionFetchError(Exception):
    """Raised when the extension ZIP cannot be fetched."""


def _clear_cache() -> None:
    """Reset the module-level cache and lock (test helper)."""
    global _zip_cache, _fetch_lock
    _zip_cache = None
    _fetch_lock = asyncio.Lock()


async def fetch_extension_zip(*, token: str, repo: str) -> bytes:
    """Download the extension ZIP from the `extension-latest` GitHub Release.

    Uses a module-level TTL cache (5 min) to avoid hammering the GitHub API
    on concurrent /extension commands. A lock prevents thundering-herd cache
    misses from issuing duplicate network requests simultaneously.

    Args:
        token: GitHub PAT with public_repo read scope.
        repo: Repository slug, e.g. ``"owner/repo"``.

    Returns:
        Raw ZIP bytes.

    Raises:
        ExtensionFetchError: If the release, asset, or download fails,
            including network-level errors.
    """
    global _zip_cache
    now = time.monotonic()
    if _zip_cache is not None and now - _zip_cache[0] < _CACHE_TTL:
        return _zip_cache[1]

    async with _fetch_lock:
        # Re-check inside the lock — another coroutine may have populated the cache
        now = time.monotonic()
        if _zip_cache is not None and now - _zip_cache[0] < _CACHE_TTL:
            return _zip_cache[1]

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(10.0)) as client:
                # Step 1: resolve asset download URL from release metadata
                release_url = f"https://api.github.com/repos/{repo}/releases/tags/extension-latest"
                resp = await client.get(release_url)
                if resp.status_code != 200:
                    raise ExtensionFetchError(
                        f"GitHub release lookup failed: HTTP {resp.status_code}"
                    )
                assets = resp.json().get("assets", [])
                zip_asset = next((a for a in assets if a["name"] == "extension.zip"), None)
                if zip_asset is None:
                    raise ExtensionFetchError("extension.zip not found in extension-latest release")

                # Step 2: download the asset bytes
                download_url = zip_asset["url"]
                dl_resp = await client.get(
                    download_url,
                    headers={"Accept": "application/octet-stream"},
                    follow_redirects=True,
                )
                if dl_resp.status_code != 200:
                    raise ExtensionFetchError(
                        f"Extension asset download failed: HTTP {dl_resp.status_code}"
                    )
                data = dl_resp.content
                if len(data) > _MAX_ZIP_BYTES:
                    raise ExtensionFetchError(
                        f"Extension ZIP too large: {len(data)} bytes (limit {_MAX_ZIP_BYTES})"
                    )
        except httpx.RequestError as exc:
            raise ExtensionFetchError(f"Network error fetching extension: {exc}") from exc

    _zip_cache = (now, data)
    return data
