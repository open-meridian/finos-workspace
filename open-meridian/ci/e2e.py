"""The workspace on a real deployment, in a headless browser.

As the deployment admin (`pat`, first_run.py), at the dashboard's own pages:
grants pat View on the workspace (a user group, an access group, a
permission on all accounts); licenses `ecb:ecb_fx` and entitles the
workspace to it. Then, as pat, through the dashboard:

1. the starter dashboard shows the latest EUR/USD with its time;
2. the data-age widget is filled;
3. the instrument lookup finds EUR/USD in the master;
4. every request the workspace's frames make is to the plugin's own origin;
5. Workspace's own UI, framed at 375, 582 and 1280 wide, does not scroll
   sideways (screenshots kept);
6. sam, who holds no level on the plugin, is refused its page;
7. with the entitlement withdrawn, the rates widget shows the refusal.

A dashboard copy reads the access records every 30 seconds, so a grant made
at one copy is refused at another until then. The run has two copies, and
opens the workspace once the grant has held at the plugin's host for that
long (`in_force`).

A plugin's workload is available before the deployment knows the plugin:
its sidecar reports once it has reached the broker, and until that first
report an access group naming the workspace is refused. The run defines its
access group once the deployment has heard from the workspace (`grant_view`,
`FIRST_REPORT`).

When a check fails, it says what the browser had: a screenshot, each frame's
address and words, and the documents last answered (`tell`).

Never prints a password. Usage: python3 e2e.py RUN_DIR
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlsplit

from playwright.sync_api import Page, sync_playwright

DASHBOARD = "http://meridian.localhost"
INSTANCE = "workspace"
PLUGIN = f"http://{INSTANCE}.plugins.meridian.localhost"
DATASET = "ecb:ecb_fx"
RUN = Path(sys.argv[1])
SHOTS = RUN / "shots"

#: How often a dashboard copy reads the access records, in seconds.
RECORDS_READ_EVERY = 30

#: How long the workspace's first report is waited for, in seconds: its
#: sidecar reports once it has reached the broker, which is after its
#: workload is available. Until then the deployment does not know the
#: workspace or its roles.
FIRST_REPORT = 300

#: What the deployment answers an access group naming a plugin it has not
#: heard from yet.
NOT_REPORTED = f"no plugin {INSTANCE} has reported"

#: Each document a watched page's frames were answered, oldest first.
DOCUMENTS: list[str] = []


def say(text: str) -> None:
    print(f"e2e: {text}", flush=True)


def until(what: str, seconds: float, check, every: float = 3.0):
    start = time.time()
    while time.time() - start < seconds:
        found = check()
        if found:
            say(f"{what} after {round(time.time() - start)}s")
            return found
        time.sleep(every)
    raise SystemExit(f"e2e: {what} never happened in {seconds}s")


def brief(url: str) -> str:
    """An address without its query's values: a one-time code is one."""
    parts = urlsplit(url)
    keys = ",".join(sorted({key for key, _ in parse_qsl(parts.query, keep_blank_values=True)}))
    host = f"{parts.scheme}://{parts.netloc}" if parts.netloc else ""
    return f"{host}{parts.path}" + (f"?{keys}" if keys else "")


def words(html: str, most: int = 400) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())[:most]


def watch(page: Page) -> None:
    def answered(response) -> None:
        if response.request.resource_type == "document":
            DOCUMENTS.append(f"{response.status} {brief(response.url)}")

    page.on("response", answered)


def tell(page: Page, name: str) -> None:
    """What the browser had when a check failed."""
    try:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"failed-{name}.png"), full_page=True)
        say(f"failed: a screenshot kept as shots/failed-{name}.png")
    except Exception as failed:  # the page may be gone
        say(f"failed: no screenshot of {name}: {failed}")
    for at, frame in enumerate(page.frames):
        try:
            text = " ".join(frame.inner_text("body", timeout=2000).split())[:600]
        except Exception as failed:
            text = f"(its words could not be read: {type(failed).__name__})"
        say(f"failed: {name} frame {at} at {brief(frame.url)}: {text}")
    for line in DOCUMENTS[-16:]:
        say(f"failed: a document answered {line}")


def sign_in(page: Page, person_file: str) -> None:
    person = json.loads((RUN / person_file).read_text())
    page.goto(f"{DASHBOARD}/sign-in")
    page.fill("#name", person["name"])
    page.fill("#password", person["password"])
    with page.expect_navigation():
        page.click("button[type=submit]")


def token(page: Page, path: str) -> str:
    page.goto(f"{DASHBOARD}{path}")
    return page.get_attribute("input[name=form_token]", "value", timeout=30_000) or ""


def send(page: Page, path: str, fields: dict[str, str]):
    """A form as a browser posts it. Returns the answer, unjudged."""
    return page.request.post(f"{DASHBOARD}{path}", form=fields, max_redirects=0)


def post(page: Page, path: str, fields: dict[str, str], what: str) -> None:
    """A form posted (`send`), and its answer held to having been taken."""
    taken(page, path, send(page, path, fields), what)


def taken(page: Page, path: str, answer, what: str) -> None:
    if answer.status not in (200, 302, 303):
        said = re.sub(r"<[^>]+>", " ", answer.text())
        raise SystemExit(f"e2e: {what} answered {answer.status}: {' '.join(said.split())[:400]}")
    if answer.status == 200:
        say(f"{what}: 200")
        return
    # Where the form sent the browser, and what that page says of it.
    where = answer.headers.get("location", "")
    landed = page.request.get(urljoin(f"{DASHBOARD}{path}", where))
    html = landed.text()
    notices = re.findall(r"<p class=\"notice[^\"]*\">(.*?)</p>", html, flags=re.S)
    told = " | ".join(words(each) for each in notices) or f"no notice; {words(html, 160)}"
    say(f"{what}: {answer.status} to {brief(where)}, which answers {landed.status}: {told}")


def option(page: Page, select: str, name: str) -> str:
    page.goto(f"{DASHBOARD}/admin")
    values = page.eval_on_selector_all(
        f"select[name={select}] option",
        "(options, name) => options.filter(o => o.textContent.trim() === name).map(o => o.value)",
        name,
    )
    if not values:
        raise SystemExit(f"e2e: no {select} named {name!r} on the admin page")
    return values[0]


def grant_view(page: Page) -> None:
    form = token(page, "/admin")
    post(page, "/admin/user-groups", {"form_token": form, "name": "Workspace readers", "login": "local|pat"},
         "a user group of pat")
    access(page)
    post(page, "/admin/permissions", {
        "form_token": form,
        "user_group_id": option(page, "user_group_id", "Workspace readers"),
        "account_group_id": "all-accounts",
        "access_group_id": option(page, "access_group_id", "Workspace view"),
    }, "the permission")


def access(page: Page) -> None:
    """The access group naming the workspace. While the deployment answers
    that it does not know the workspace yet (`NOT_REPORTED`), the form is
    posted again, a refused one having changed nothing, until the deployment
    has heard from it, at most `FIRST_REPORT` seconds. Any other refusal
    fails at once."""

    def sent():
        form = token(page, "/admin")
        answer = send(page, "/admin/access-groups",
                      {"form_token": form, "name": "Workspace view", "entries": f"{INSTANCE} reporting read"})
        if answer.status == 400 and NOT_REPORTED in words(answer.text(), 4000):
            say(f"Workspace view not defined yet: {NOT_REPORTED}")
            return None
        return answer

    answer = until(f"the deployment hearing from {INSTANCE}", FIRST_REPORT, sent, every=2)
    taken(page, "/admin/access-groups", answer, "an access group, View on the workspace")


def license_and_entitle(page: Page) -> None:
    def listed():
        page.goto(f"{DASHBOARD}/admin/data-sources")
        return DATASET in page.content()

    until(f"{DATASET} listed on Data sources", 600, listed, every=10)
    form = token(page, "/admin/data-sources")
    post(page, "/admin/data-sources/licence", {
        "form_token": form, "dataset": DATASET, "kept": "1", "retention_days": "0",
        "display": "1", "derived_use": "1", "note": "The workspace's CI run",
    }, f"the licence of {DATASET}")
    entitle(page, allowed=True)


def entitle(page: Page, allowed: bool) -> None:
    form = token(page, "/admin/data-sources")
    fields = {"form_token": form, "dataset": DATASET, "instance": INSTANCE, "note": "The workspace's CI run"}
    if allowed:
        fields["allowed"] = "1"
    post(page, "/admin/data-sources/entitlement", fields,
         f"{'the entitlement' if allowed else 'the entitlement withdrawn'}: {INSTANCE} to {DATASET}")


def in_force(page: Page) -> None:
    """pat's View on the workspace, in force at every dashboard copy: the
    workspace's page answered at the plugin's host, through the way in the
    area's frame takes, on every asking for as long as a copy goes between
    two reads of the access records."""
    held_since: list[float] = []

    def held():
        answer = page.request.get(f"{DASHBOARD}/plugins/{INSTANCE}/enter?level=read")
        if answer.status != 200 or not answer.url.startswith(f"{PLUGIN}/app"):
            say(f"View is not in force everywhere yet: {answer.status} at {brief(answer.url)}: "
                f"{words(answer.text(), 200)}")
            held_since.clear()
            return False
        held_since.append(time.time())
        return time.time() - held_since[0] >= RECORDS_READ_EVERY

    until("pat's View in force at the workspace's host", 120, held, every=2)


def open_workspace(page: Page) -> None:
    """The workspace's area at View, its front end framed, the starter
    dashboard opened from its Apps page."""

    def shown():
        page.goto(f"{DASHBOARD}/plugins/{INSTANCE}?level=read")
        return page.query_selector("iframe[data-plugin-frame]")

    until("the workspace's page shown in its area", 180, shown)
    app = until("Workspace's Apps page", 120, lambda: next(
        (f for f in page.frames if f.url.startswith(PLUGIN) and "/app" in f.url), None), every=2)
    app.get_by_text("FX reference rates", exact=True).first.click(timeout=60_000)


def widget_texts(page: Page, marker: str) -> list[str]:
    """The words of each frame naming `marker`, in any case: a widget's
    headings are drawn in capitals, and inner text is as drawn."""
    found = []
    for frame in page.frames:
        try:
            text = frame.inner_text("body", timeout=1000)
        except Exception:
            continue
        if marker.lower() in text.lower():
            found.append(text)
    return found


def widget_text(page: Page, marker: str) -> str:
    return next(iter(widget_texts(page, marker)), "")


def rates_row(page: Page) -> str:
    """The table's EUR/USD row; the chart names the business date too, and
    has no row."""
    for text in widget_texts(page, "Business date"):
        match = re.search(r"EUR/USD\s+([0-9.]+)\s+(\d{4}-\d\d-\d\d)\s+(\S+Z)\s+(\S+)", text)
        if match:
            return match.group(0)
    return ""


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        admin = browser.new_context(viewport={"width": 1280, "height": 900})
        page = admin.new_page()
        watch(page)
        try:
            checks(browser, page)
        except BaseException:
            tell(page, "admin")
            raise
        browser.close()
    say("every check held")


def checks(browser, page: Page) -> None:
    """Every check, as pat and then as sam."""
    sign_in(page, "person.json")
    grant_view(page)
    license_and_entitle(page)
    in_force(page)

    asked: list[tuple[str, str]] = []
    page.on("request", lambda r: asked.append((r.frame.url if r.frame else "", r.url)))
    open_workspace(page)

    # 1. EUR/USD with its time, from the lake; reloaded until the ECB's
    # rates have reached it.
    def eur_usd():
        page.wait_for_timeout(8000)
        row = rates_row(page)
        if not row:
            open_workspace(page)
        return row

    say(f"the rates widget: {until('EUR/USD with its time', 900, eur_usd, every=15)}")
    # 2. The data age.
    ages = until("the data-age widget filled", 120, lambda: DATASET in widget_text(page, "Last heard")
                 and widget_text(page, "Last heard"))
    say(f"the data-age widget: {' '.join(ages.split())[:200]}")
    # 3. The lookup.
    lookup = until("the lookup's EUR/USD", 120, lambda: (t := widget_text(page, "Identifiers"))
                   and "iso4217:EUR" in t and "iso4217:USD" in t and t)
    say(f"the lookup: {' '.join(lookup.split())[:200]}")

    # 4. No route out.
    out = sorted({url for frame, url in asked
                  if frame.startswith(PLUGIN) and not url.startswith((PLUGIN, "data:", "blob:"))})
    if out:
        raise SystemExit(f"e2e: the workspace's frames asked other origins: {out}")
    mine = sum(1 for frame, _ in asked if frame.startswith(PLUGIN))
    say(f"the workspace's frames made {mine} requests, every one to {PLUGIN}")

    # 5. Workspace's own UI at each width, framed by the dashboard.
    for width in (375, 582, 1280):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(3000)
        app = next(f for f in page.frames if f.url.startswith(PLUGIN))
        wide, room = app.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        page.screenshot(path=str(SHOTS / f"workspace-{width}.png"))
        if wide > room:
            raise SystemExit(f"e2e: Workspace's UI scrolls sideways at {width}: {wide}px in {room}px")
        say(f"at {width} wide: {wide}px in {room}px, no sideways scroll")

    # 6. Somebody holding no level is refused.
    other = browser.new_context().new_page()
    sign_in(other, "person2.json")
    answer = other.goto(f"{DASHBOARD}/plugins/{INSTANCE}?level=read")
    if other.query_selector("iframe[data-plugin-frame]") or (answer and answer.status < 400):
        tell(other, "sam")
        raise SystemExit(f"e2e: sam was not refused the workspace ({answer.status if answer else 'no answer'})")
    said = " ".join(other.inner_text("body").split())[:160]
    say(f"sam, holding no level, refused: {answer.status} {said}")

    # 7. The entitlement withdrawn: the refusal, not an empty table.
    entitle(page, allowed=False)
    page.set_viewport_size({"width": 1280, "height": 900})

    def refused():
        open_workspace(page)
        page.wait_for_timeout(8000)
        return next((text for text in widget_texts(page, "Refused") if "not entitled" in text.lower()), "")

    said = until("the rates widget's refusal", 180, refused, every=5)
    page.screenshot(path=str(SHOTS / "refused.png"))
    say(f"withdrawn: {' '.join(said.split())[:200]}")


if __name__ == "__main__":
    main()
