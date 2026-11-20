"""Workspace's own UI in a browser, on the wrapper with the stand-in
sidecar (tests/dev.py): at 375, 582 and 1280 wide, no horizontal scroll;
the starter dashboard shows EUR/USD; every request the page makes is to its
own origin; and with the entitlement withdrawn the rates show the refusal.

Needs the front end built into web/ (open-meridian/ci/frontend.sh) and
Playwright's Chromium; skipped without them. Screenshots go to
$BROWSER_SHOTS when it is set.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).parent
WEB = HERE.parent / "web"
WIDTHS = (375, 582, 1280)
#: The width this workspace is stated to work at, at the least (its docs).
MINIMUM = 375

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not (WEB / "index.html").is_file(), reason="the front end is not built")


def free_port() -> int:
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        return held.getsockname()[1]


def serve(entitled: bool):
    port = free_port()
    env = dict(os.environ, WORKSPACE_WEB=str(WEB), WORKSPACE_ENTITLED="1" if entitled else "0")
    process = subprocess.Popen([sys.executable, str(HERE / "dev.py"), str(port)], env=env)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return process, base
        except OSError:
            time.sleep(0.1)
    process.kill()
    raise RuntimeError("the wrapper did not start")


def open_dashboard(page, base: str) -> None:
    page.goto(base + "/")
    page.wait_for_url("**/app", timeout=30_000)
    page.get_by_text("FX reference rates", exact=True).first.click(timeout=30_000)
    page.wait_for_selector("iframe", timeout=30_000)


def frame_text(page, title: str) -> str:
    """The text of the widget titled so: its view is a frame of its own."""
    for _ in range(60):
        for frame in page.frames:
            try:
                text = frame.inner_text("body", timeout=500)
            except Exception:
                continue
            if title in text:
                return text
        page.wait_for_timeout(500)
    return ""


def test_the_starter_dashboard_at_each_width_reaches_only_its_own_origin() -> None:
    process, base = serve(entitled=True)
    shots = os.environ.get("BROWSER_SHOTS")
    try:
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch()
            for width in WIDTHS:
                page = browser.new_page(viewport={"width": width, "height": 900})
                asked: list[str] = []
                page.on("request", lambda r: asked.append(r.url))
                open_dashboard(page, base)
                assert frame_text(page, "EUR/USD"), f"no EUR/USD at {width}"
                page.wait_for_timeout(1000)
                scroll = page.evaluate("document.documentElement.scrollWidth")
                assert scroll <= width, f"{scroll}px wide at {width}"
                if shots:
                    Path(shots).mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=f"{shots}/dashboard-{width}.png")
                elsewhere = sorted({u for u in asked if not u.startswith(base) and not u.startswith(("data:", "blob:", "about:"))})
                assert elsewhere == [], elsewhere
                page.close()
            browser.close()
    finally:
        process.kill()


def test_with_the_entitlement_withdrawn_the_rates_show_the_refusal() -> None:
    process, base = serve(entitled=False)
    try:
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            open_dashboard(page, base)
            text = frame_text(page, "Refused")
            assert "not entitled to ecb:ecb_fx" in text
            browser.close()
    finally:
        process.kill()
