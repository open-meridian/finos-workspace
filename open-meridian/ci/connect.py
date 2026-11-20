"""The person allows `meridian connect`: the CLI printed where to sign in; sign
in there in a headless browser, as the one person first_run.py made, and allow
it (as meridian-desktop's ci/connect.mjs does). Never prints the password or
the link's code. Usage: python3 connect.py CONNECT_LOG PERSON_JSON DASHBOARD"""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

log, person_file, dashboard = sys.argv[1:4]
person = json.loads(Path(person_file).read_text())
url = None
for _ in range(300):
    text = Path(log).read_text() if Path(log).exists() else ""
    url = next((w for w in text.split() if w.startswith(f"{dashboard}/oauth/authorize?")), None)
    if url:
        break
    time.sleep(1)
if not url:
    sys.exit("connect: the CLI never said where to sign in")
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(url)
    page.fill("#name", person["name"])
    page.fill("#password", person["password"])
    page.click("button[type=submit]")
    page.click("button[name=decision][value=allow]", timeout=60_000)
    page.wait_for_load_state()
    browser.close()
print("connect: allowed")
