"""The plugin's page: FINOS Workspace's front end, and what it asks of the
plugin's own origin.

Two tabs are declared, as every page is:

- **Workspace** (`/`), under Open and View: the front end. Its own routes
  (`/app/...`), its files and its `/app` API (under `/api`) are served under
  the same levels, by `dispatch` below, since the SDK's pages declare exact
  paths and the front end has hundreds of files.
- **Datasets** (`/datasets`), under Manage: the reporting role's common page,
  each dataset the plugin reads and whether it is entitled to it.

Each read the Workspace page shows is also a read tool on the deployment's
MCP surface, under the same levels (Open and View): `read_fx_rates` (the
rates table and chart), `read_dataset_ages` (the dataset ages) and
`read_instrument` (the instrument lookup). Each reads what its widget reads,
through the same role class, and is refused as its widget is.

Who is asking is the `Meridian-Caller` header the sidecar forwarded, every
time. Nothing here sets a cookie or keeps a session. A request that changes
something (any method but GET and HEAD) must carry `X-Workspace-Client: web`,
which Workspace's front end sends to its API and a page of another origin
cannot send without a preflight this plugin never answers.

Every answer carries the Content-Security-Policy: the page reaches only its
own origin (`connect-src 'self'`), and loads images and fonts only from it
or inline.
"""

from __future__ import annotations

import json
import logging
import mimetypes
from dataclasses import asdict, dataclass, field
from pathlib import Path

import meridian
from meridian.roles import reporting
from meridian.v1 import sidecar_pb2

from . import api
from .lake import Age, Found, Lake, Rate, Refused, now_ns

log = logging.getLogger("workspace")

TITLE = "Workspace"

#: What Workspace's tab bar and title name: the deployment's page, not upstream.
WL_NAME = "Open Meridian workspace"

#: Where the front end's built files are: the image's `/plugin/web`.
WEB = Path("/plugin/web")

#: The stylesheet mapping Workspace's look onto the kit's tokens.
THEME = Path(__file__).parent / "theme.css"
THEME_PATH = "/open-meridian/theme.css"

#: The levels the front end is served under: Open and View.
SERVED = frozenset({sidecar_pb2.ACCESS_LEVEL_WRITE, sidecar_pb2.ACCESS_LEVEL_READ})

#: The front end's own pages this never serves: its sign-in, password reset,
#: 2FA, admin area and OAuth callback.
NEVER_SHOWN = ("/login", "/reset-password", "/2fa", "/admin", "/oauth")

CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval' blob:",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "frame-src 'self' blob: data:",
        "worker-src 'self' blob:",
        "media-src 'self' data: blob:",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
    ]
)

#: Workspace's runtime configuration, as its `config.js` would set it: the API
#: on this origin, no sign-in of its own, no copilot, no companion mode, no
#: outside documentation, no scripts in HTML widgets.
CONFIG = {
    "urls": {"backend": api.PREFIX, "ai": ""},
    "authentication": {
        "allowEmailLogin": False,
        "identityProviders": [],
        "sendUserEmailAsHeader": False,
    },
    "authProviders": {"googleClientId": ""},
    "copilot": {
        "enabled": False,
        "defaultCopilot": False,
        "documentationLinks": False,
        "aiEnhancements": False,
        "saveSkillFromChat": False,
        "showCustomKey": False,
    },
    "ui": {
        "showCompanionMode": False,
        "showMinimizeWidget": True,
        "showExternalDocLinks": False,
        "showHelpDocumentation": False,
        "showChangelog": False,
        "showCopilotSwitcher": False,
        "showRemoveFromOrg": False,
        "defaultTheme": "dark",
    },
    "data": {"allowHtmlJsExecution": False},
    "links": {"docsUrl": ""},
    "contact": {"supportEmail": ""},
    "whiteLabel": {"name": WL_NAME, "stylesheet": THEME_PATH},
}

CONFIG_JS = ("window.__APP_CONFIG__ = " + json.dumps(CONFIG, indent=2) + ";\n").encode()

mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("font/woff2", ".woff2")


def _headers(cache: str) -> tuple[tuple[str, str], ...]:
    return (
        ("content-security-policy", CSP),
        ("x-content-type-options", "nosniff"),
        ("referrer-policy", "no-referrer"),
        ("cache-control", cache),
    )


def _bytes(body: bytes, content_type: str, status: int = 200, cache: str = "no-store") -> meridian.Response:
    return meridian.Response(body, status, content_type, _headers(cache))


def _said(status: int, text: str) -> meridian.Response:
    return _bytes(text.encode(), "text/plain; charset=utf-8", status)


class Workspace(meridian.Pages):
    """The declared tabs, and Workspace's front end and `/app` API under them."""

    def __init__(self, lake: Lake | None = None, web: Path = WEB) -> None:
        super().__init__(TITLE, templates=Path(__file__).parent / "templates")
        self.lake = lake or Lake()
        self.web = web

    async def dispatch(self, request: meridian.Request) -> meridian.Response:
        method = request.method.upper()
        declared = (request.path, "GET" if method == "HEAD" else method)
        if declared in self._declared_paths():
            return await super().dispatch(request)
        if request.caller.level not in SERVED:
            return _said(403, "This page is served under Open and View.")
        answer = await self._serve(request, method)
        if method == "HEAD":
            return meridian.Response(b"", answer.status, answer.content_type, answer.headers)
        return answer

    def _declared_paths(self) -> set[tuple[str, str]]:
        tabs = {(page.path, "GET") for page in self.declared}
        return tabs | {(tool.path, tool.method) for tool in self.tools}

    async def _serve(self, request: meridian.Request, method: str) -> meridian.Response:
        path = request.path
        if path == api.PREFIX or path.startswith(api.PREFIX + "/"):
            if method not in ("GET", "HEAD") and request.headers.get("x-workspace-client") != "web":
                return _said(403, "A change is sent by this workspace's own page.")
            answered = await api.answer(
                self.lake, request.caller, method, path[len(api.PREFIX) :], request.body
            )
            return _bytes(answered.body, answered.content_type, answered.status)
        if method not in ("GET", "HEAD"):
            return _said(405, "Only the API takes a change.")
        if path == "/config.js":
            return _bytes(CONFIG_JS, "application/javascript")
        if path == THEME_PATH:
            return _bytes(THEME.read_bytes(), "text/css; charset=utf-8")
        if any(path == each or path.startswith(each + "/") for each in NEVER_SHOWN):
            return _said(404, "Not served: this workspace's sign-in is the deployment's.")
        found = self._file(path)
        if found is not None:
            kind = mimetypes.guess_type(found.name)[0] or "application/octet-stream"
            hashed = found.parent == self.web and found.name.count(".") >= 2
            cache = "public, max-age=31536000, immutable" if hashed else "no-cache"
            return _bytes(found.read_bytes(), kind, cache=cache)
        if "." in path.rsplit("/", 1)[-1]:
            return _said(404, "No such file.")
        return self.index()

    def _file(self, path: str) -> Path | None:
        if path in ("", "/", "/index.html"):
            return None
        target = (self.web / path.lstrip("/")).resolve()
        if self.web.resolve() not in target.parents or not target.is_file():
            return None
        return target

    def index(self) -> meridian.Response:
        """The front end's page, for any of its own routes."""
        return _bytes((self.web / "index.html").read_bytes(), "text/html; charset=utf-8")


pages = Workspace()


def use(lake: Lake) -> None:
    """The role class the pages read through: the one the plugin runs."""
    pages.lake = lake


@pages.page("/", TITLE, levels=["write", "read"])
async def workspace(request: meridian.Request) -> meridian.Response:
    """FINOS Workspace's front end: dashboards of widgets reading the lake,
    whose home is `/app` (its own `/` sends a visitor to its sign-in)."""
    query = "&".join(f"{key}={value}" for key, value in request.query.items() if key.startswith("om-"))
    where = "/app" + (f"?{query}" if query else "")
    return meridian.Response(b"", 302, "text/plain", (*_headers("no-store"), ("location", where)))


@pages.page(
    "/datasets",
    "Datasets",
    levels="admin",
    answers=reporting.DatasetsRead,
    name="read_datasets",
)
async def datasets(request: meridian.Request) -> meridian.Response:
    """Each dataset this plugin reads, whether it is entitled to it and to
    which fields."""
    read = await pages.lake.list_datasets()
    mine = {each.dataset: each for each in read.entitlements}
    said = reporting.DatasetsRead(
        datasets=[
            reporting.DatasetRead(
                dataset=ref.dataset,
                entitled=ref.dataset in mine and mine[ref.dataset].allowed,
                fields=list(mine[ref.dataset].fields) if ref.dataset in mine else [],
                misses=ref.miss_count,
            )
            for ref in read.datasets
        ]
    )
    return pages.answer("datasets.html", said)


#: The read tools' paths: under none of the front end's own.
TOOLS = "/tools"

#: The levels the front end is served under, which its reads' tools serve.
READ_LEVELS = ["write", "read"]


@dataclass(frozen=True)
class RatesRead:
    """The latest reference rates, as the rates table and chart show them."""

    rates: list[Rate] = field(default_factory=list)


@dataclass(frozen=True)
class AgesRead:
    """Each dataset this plugin may read, as the dataset ages widget shows it."""

    datasets: list[Age] = field(default_factory=list)


@dataclass(frozen=True)
class LookupAsked:
    """What the instrument lookup is asked."""

    query: str = field(
        metadata={
            "description": "An ISO 4217 code or a pair of them (EUR/USD), a FIGI, an ISIN, "
            "a ticker, or an instrument's ID",
            "max_length": 64,
        }
    )


@dataclass(frozen=True)
class LookupRead:
    """The master's records for what was asked, as the lookup widget shows them."""

    found: list[Found] = field(default_factory=list)


def _rows(records: list) -> list[dict]:
    return [{key: ("" if value is None else value) for key, value in asdict(each).items()} for each in records]


@pages.route(f"{TOOLS}/fx-rates", levels=READ_LEVELS, answers=RatesRead, name="read_fx_rates")
async def read_fx_rates(request: meridian.Request) -> meridian.Response:
    """The latest reference rate of the euro in each currency the lake holds,
    with its business date, its time and the dataset it came from: what the
    Workspace page's rates table and chart show."""
    try:
        rates = await pages.lake.rates()
    except Refused as why:
        pages.refuse(str(why), reason="declined")
    columns = [
        ("pair", "Pair"),
        ("rate", "Rate"),
        ("business_date", "Business date"),
        ("valid_from", "Time"),
        ("dataset", "Source"),
    ]
    return pages.answer(
        "read.html", RatesRead(rates=rates), heading="Latest FX reference rates",
        columns=columns, rows=_rows(rates), empty="The lake holds no reference rate yet.",
    )


@pages.route(f"{TOOLS}/dataset-ages", levels=READ_LEVELS, answers=AgesRead, name="read_dataset_ages")
async def read_dataset_ages(request: meridian.Request) -> meridian.Response:
    """Each dataset this plugin may read: whether it is entitled, when its
    source was last heard and how long ago, as the Workspace page's dataset
    ages widget shows it."""
    ages = await pages.lake.ages(now_ns())
    columns = [
        ("dataset", "Dataset"),
        ("vendor", "Vendor"),
        ("entitled", "Entitled"),
        ("alive_at", "Last heard"),
        ("age_seconds", "Age (s)"),
    ]
    return pages.answer(
        "read.html", AgesRead(datasets=ages), heading="Dataset ages",
        columns=columns, rows=_rows(ages), empty="This workspace is not entitled to any dataset yet.",
    )


@pages.route(
    f"{TOOLS}/instrument",
    levels=READ_LEVELS,
    params=LookupAsked,
    answers=LookupRead,
    name="read_instrument",
)
async def read_instrument(request: meridian.Request) -> meridian.Response:
    """The deployment's master records for an identifier, as the Workspace
    page's instrument lookup shows them."""
    asked = request.params.query if request.params is not None else ""
    try:
        found = await pages.lake.lookup(asked)
    except Refused as why:
        pages.refuse(str(why), reason="declined")
    columns = [
        ("asked", "Asked"),
        ("instrument_id", "Instrument"),
        ("description", "Description"),
        ("asset_class", "Asset class"),
        ("currency", "Currency"),
    ]
    return pages.answer(
        "read.html", LookupRead(found=found), heading="Instrument lookup",
        columns=columns, rows=_rows(found), empty=f"The master holds no instrument for {asked!r}.",
    )
