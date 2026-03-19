"""
session_recorder.py
───────────────────
A passive browser session recorder using Camoufox.

Captures exactly what Chrome DevTools captures — nothing more, nothing less:
  • Requests  — method, URL, headers, body
  • Responses — status, headers, body
  • Navigations
  • Cookies (final jar)

No JS injection. No DOM evaluation. No data manipulation.
The recorder observes and writes. Analysis is the agent's job.

────────────────────────────────────────────────────────────
INSTALL
────────────────────────────────────────────────────────────
    pip install camoufox
    camoufox fetch          # download the browser binary once

USAGE
────────────────────────────────────────────────────────────
    python session_recorder.py --url https://example.com
    python session_recorder.py --url https://example.com --headless
    python session_recorder.py --url https://example.com --out my_session
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_body(raw: bytes) -> str | dict:
    """Decode bytes to str. Return base64 dict if not UTF-8."""
    try:
        return raw.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        return {"_encoding": "base64", "data": base64.b64encode(raw).decode("ascii")}


def _try_json(text: str) -> Optional[dict | list]:
    try:
        return json.loads(text)
    except Exception:
        return None


def _is_text(content_type: str) -> bool:
    return any(t in content_type for t in
               ("json", "text", "xml", "javascript", "form"))


# ══════════════════════════════════════════════════════════════════════════════
#  Session store  — plain data container, zero logic
# ══════════════════════════════════════════════════════════════════════════════

class Session:
    def __init__(self):
        self.started_at  = _ts()
        self.ended_at: Optional[str] = None
        self.navigations: list[dict] = []
        self.requests:    list[dict] = []
        self.responses:   list[dict] = []
        self.cookies:     list[dict] = []

    def to_dict(self) -> dict:
        return {
            "meta": {
                "started_at":        self.started_at,
                "ended_at":          self.ended_at,
                "total_navigations": len(self.navigations),
                "total_requests":    len(self.requests),
                "total_responses":   len(self.responses),
                "total_cookies":     len(self.cookies),
            },
            "navigations": self.navigations,
            "requests":    self.requests,
            "responses":   self.responses,
            "cookies":     self.cookies,
        }

    def save(self, path: str):
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        print(f"  📄  JSON → {path}")

    def summary(self):
        m = self.to_dict()["meta"]
        print("\n╔══════════════════════════════════════╗")
        print("║         SESSION SUMMARY              ║")
        print("╠══════════════════════════════════════╣")
        for k, v in m.items():
            if k not in ("started_at", "ended_at"):
                label = k.replace("total_", "").replace("_", " ").title()
                print(f"║  {label:<28} {str(v):>5}  ║")
        print("╚══════════════════════════════════════╝\n")


# ══════════════════════════════════════════════════════════════════════════════
#  Event handlers  — each just records what it receives
# ══════════════════════════════════════════════════════════════════════════════

def on_request(session: Session, request):
    body = None
    try:
        buf = request.post_data_buffer
        if buf:
            body = _read_body(buf)
    except Exception:
        pass

    session.requests.append({
        "ts":            _ts(),
        "method":        request.method,
        "url":           request.url,
        "resource_type": request.resource_type,
        "headers":       dict(request.headers),
        "body":          body,
    })


async def on_response(session: Session, response):
    body_raw  = None
    body_text = None
    body_json = None

    ct = response.headers.get("content-type", "")
    if _is_text(ct):
        try:
            raw       = await response.body()
            body_text = _read_body(raw)
            if isinstance(body_text, str) and "json" in ct:
                body_json = _try_json(body_text)
        except Exception:
            pass

    session.responses.append({
        "ts":           _ts(),
        "status":       response.status,
        "url":          response.url,
        "content_type": ct,
        "headers":      dict(response.headers),
        "body_text":    body_text[:4000] if isinstance(body_text, str) else body_text,
        "body_json":    body_json,
    })


def on_navigation(session: Session, frame):
    # main frame only
    if frame.parent_frame is None:
        session.navigations.append({
            "ts":  _ts(),
            "url": frame.url,
        })


# ══════════════════════════════════════════════════════════════════════════════
#  Browser session
# ══════════════════════════════════════════════════════════════════════════════

async def run(args):
    from camoufox.async_api import AsyncCamoufox

    session = Session()

    print(f"\n🦊  Camoufox Session Recorder")
    print(f"    Target  : {args.url}")
    print(f"    Headless: {args.headless}")
    print(f"    Output  : {args.out}.json")
    print(f"\n    Browse freely. Close the window or Ctrl+C to stop.\n")

    async with AsyncCamoufox(
        headless=args.headless,
        viewport={"width": 1280, "height": 800},
    ) as browser:
        page = await browser.new_page()

        # Attach at page level — more reliable across Camoufox versions
        page.on("request",       lambda r: on_request(session, r))
        page.on("response",      lambda r: asyncio.ensure_future(on_response(session, r)))
        page.on("framenavigated", lambda f: on_navigation(session, f))

        await page.goto(args.url, wait_until="domcontentloaded")

        try:
            while not page.is_closed():
                await asyncio.sleep(1)
        except (asyncio.CancelledError, Exception):
            pass

        # Final cookie snapshot
        try:
            session.cookies = await browser.cookies()
        except Exception:
            pass

    session.ended_at = _ts()
    session.summary()
    session.save(f"{args.out}.json")
    print(f"\n✅  Done.\n")


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Passive browser session recorder")
    parser.add_argument("--url",      default="about:blank", help="Starting URL")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--out",      default="session_report", help="Output file prefix")
    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n👋  Stopped.")


if __name__ == "__main__":
    main()