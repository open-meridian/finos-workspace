"""The wrapper, against the stand-in sidecar: the `/app` subset and nothing
else, the session from the assertion, the widgets' reads and refusals, the
levels, and the Content-Security-Policy. `meridian plugin check
--run-tests` and the fork's CI run these; none needs a deployment."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from meridian.testing import PageClient

sys.path.insert(0, str(Path(__file__).parent))

from standin import DATASET, Sidecar  # noqa: E402

from workspace import api, widgets  # noqa: E402
from workspace.lake import Lake  # noqa: E402
from workspace.pages import CSP, pages, use  # noqa: E402


#: The whole subset: what the front end calls at start and on the dashboard
#: screens, found by recording a browser (open-meridian/PROVENANCE.md).
SUBSET = {
    ("GET", "/app/session"),
    ("GET", "/app/dash/validate-and-sync"),
    ("GET", "/app/data-connectors/api-source"),
    ("POST", f"/app/data-connectors/api-source/{widgets.SOURCE_ID}/request"),
    ("GET", "/app/resource-permissions"),
    ("GET", "/app/widget-plugins"),
    ("GET", "/app/widget-plugins/widgets-schema"),
}

#: Routes upstream's backend-api serves that are never served here.
NEVER = [
    ("POST", "/app/login"),
    ("POST", "/app/logout"),
    ("POST", "/app/google-auth"),
    ("POST", "/app/sign-in/google/start"),
    ("PUT", "/app/2fa"),
    ("POST", "/app/reset-password"),
    ("GET", "/admin/users"),
    ("POST", "/admin/role"),
    ("POST", "/app/dash/abc/share"),
    ("GET", "/app/user-apps/abc/shares"),
    ("POST", "/app/copilot/token"),
    ("GET", "/app/copilot-keys"),
    ("GET", "/app/custom-copilot"),
    ("POST", "/app/mcp-servers"),
    ("POST", "/app/mcp-proxy"),
    ("POST", "/app/mcp-oauth/start"),
    ("GET", "/app/workspace-mcp/tokens"),
    ("POST", "/app/workspace-mcp/bridge/session/start"),
    ("POST", "/app/files"),
    ("GET", "/app/usage"),
    ("POST", "/app/widget-plugins/report"),
    ("GET", "/plugins"),
]


@pytest.fixture(autouse=True)
def web(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html><title>Workspace</title>")
    (tmp_path / "index.abc123.js").write_text("export {}")
    (tmp_path / "widgets-schema.json").write_text('{"$id":"urn:test","x-types":["html"],"definitions":{}}')
    monkeypatch.setattr(pages, "web", tmp_path)
    monkeypatch.setattr(api, "SCHEMA", tmp_path / "widgets-schema.json")


def client(sidecar: Sidecar | None = None) -> tuple[PageClient, Sidecar]:
    sidecar = sidecar or Sidecar()
    use(sidecar.bind(Lake()))
    return PageClient(pages, sidecar), sidecar


def call(c: PageClient, method: str, path: str, body: dict | None = None, level: str = "read"):
    headers = {"x-workspace-client": "web"} if method != "GET" else {}
    from meridian.pages import Request

    import asyncio

    request = Request(
        method=method,
        path=path,
        caller=c.caller(level),
        plugin=c.plugin,
        body=json.dumps(body).encode() if body is not None else b"",
        headers=headers,
    )
    return asyncio.run(pages.dispatch(request))


def widget(c: PageClient, name: str, query: str = "", level: str = "read"):
    url = f"{widgets.SOURCE_URL}/{name}?theme=light{query}"
    return call(c, "POST", f"/api/app/data-connectors/api-source/{widgets.SOURCE_ID}/request", {"url": url}, level)


def test_the_subset_is_seven_routes_and_each_is_served() -> None:
    assert len(SUBSET) == 7
    for method, path in SUBSET:
        assert api.served(method, path), (method, path)


@pytest.mark.parametrize(("method", "path"), NEVER)
def test_workspace_identity_admin_sharing_and_agent_surface_are_never_served(method, path) -> None:
    c, _ = client()
    assert not api.served(method, path)
    assert call(c, method, "/api" + path, {}).status == 404


def test_the_session_is_the_assertions_person_and_no_one_else() -> None:
    c, _ = client()
    session = json.loads(call(c, "GET", "/api/app/session").body)
    assert session["uuid"] == "local|ada"
    assert session["username"] == "Ada Park"
    assert session["access"] == {"user_type": "User", "sharing": "none"}


def test_the_front_end_is_served_under_open_and_view_and_refused_under_manage() -> None:
    c, _ = client()
    for level in ("write", "read"):
        assert c.get("/", level).status == 302
        assert call(c, "GET", "/app/rates", level=level).status == 200
        assert call(c, "GET", "/index.abc123.js", level=level).status == 200
    assert c.get("/", "admin").status == 403
    assert call(c, "GET", "/app", level="admin").status == 403
    assert call(c, "GET", "/api/app/session", level="admin").status == 403


def test_its_own_sign_in_and_admin_pages_are_not_served() -> None:
    c, _ = client()
    for path in ("/login", "/reset-password", "/2fa", "/admin", "/admin/users", "/oauth/callback"):
        assert call(c, "GET", path).status == 404, path


def test_a_change_needs_the_pages_own_header() -> None:
    c, _ = client()
    from meridian.pages import Request

    import asyncio

    request = Request(method="POST", path="/api/app/dash/sync", caller=c.caller("read"), plugin=c.plugin, body=b"{}")
    assert asyncio.run(pages.dispatch(request)).status == 403
    assert call(c, "POST", "/api/app/dash/sync", {}).status == 200


def test_the_one_connection_is_the_lake_and_cannot_be_changed() -> None:
    c, _ = client()
    sources = json.loads(call(c, "GET", "/api/app/data-connectors/api-source").body)
    assert [s["url"] for s in sources] == ["http://lake.meridian.invalid"]
    assert call(c, "POST", "/api/app/data-connectors/api-source/new", {"url": "https://x.example"}).status == 403
    assert call(c, "DELETE", f"/api/app/data-connectors/api-source/{widgets.SOURCE_ID}", {}).status == 403
    answer = call(
        c, "POST", f"/api/app/data-connectors/api-source/{widgets.SOURCE_ID}/request", {"url": "https://example.com/x"}
    )
    assert answer.status == 403


def test_the_starter_dashboard_places_every_widget_and_no_prompt_or_agent() -> None:
    c, _ = client()
    apps = json.loads(widget(c, "apps.json").body)
    placed = {item["i"] for app in apps for tab in app["tabs"].values() for item in tab["layout"]}
    assert placed == set(widgets.WIDGETS)
    assert all(app["prompts"] == [] for app in apps)
    assert widget(c, "agents.json").status == 404


def test_the_rates_table_shows_eur_usd_with_its_time_and_source() -> None:
    c, _ = client()
    rows = json.loads(widget(c, "fx_rates_table", "&raw=true").body)
    usd = next(row for row in rows if row["pair"] == "EUR/USD")
    assert usd == {
        "pair": "EUR/USD",
        "currency": "USD",
        "rate": 1.1225,
        "business_date": "2025-11-20",
        "valid_from": "2025-11-20T15:00:00Z",
        "recorded_at": "2025-11-20T16:00:00Z",
        "dataset": DATASET,
    }
    page = widget(c, "fx_rates_table").text
    assert "<td>EUR/USD</td><td class=n>1.1225</td>" in page
    assert "<svg" in widget(c, "fx_rates_chart").text


def test_with_the_entitlement_withdrawn_each_widget_shows_the_refusal_not_an_empty_table() -> None:
    c, _ = client(Sidecar(entitled=False))
    for name in ("fx_rates_table", "fx_rates_chart"):
        page = widget(c, name).text
        assert "data-refused" in page and "not entitled to ecb:ecb_fx" in page
        assert "<table" not in page
    assert widget(c, "fx_rates_table", "&raw=true").status == 403
    assert "Not entitled" in widget(c, "dataset_ages").text


def test_with_no_dataset_listed_the_rates_show_the_refusal_as_a_deployment_answers() -> None:
    # A deployment's sidecar lists only the datasets the plugin is entitled
    # to: with the one entitlement withdrawn, none, licensed or not.
    c, _ = client(Sidecar(entitled=False, listed=False))
    for name in ("fx_rates_table", "fx_rates_chart"):
        page = widget(c, name).text
        assert "data-refused" in page and "not entitled to any dataset" in page
        assert "licensed to this" not in page and "<table" not in page
    assert widget(c, "fx_rates_table", "&raw=true").status == 403
    ages = widget(c, "dataset_ages").text
    assert "not entitled to any dataset" in ages and "<table" not in ages


def test_the_data_age_widget_is_filled() -> None:
    c, _ = client()
    rows = json.loads(widget(c, "dataset_ages", "&raw=true").body)
    assert rows[0]["dataset"] == DATASET and rows[0]["entitled"] is True
    assert rows[0]["alive_at"] == "2025-11-20T00:00:00Z" and rows[0]["age_seconds"] > 0


def test_the_lookup_finds_eur_usd_in_the_master() -> None:
    c, _ = client()
    rows = json.loads(widget(c, "instrument_lookup", "&query=EUR%2FUSD&raw=true").body)
    assert [row["instrument_id"] for row in rows] == ["INS-EUR", "INS-USD"]
    assert "holds no instrument" in widget(c, "instrument_lookup", "&query=ZZZ").text


def test_manage_shows_the_datasets_it_reads() -> None:
    c, _ = client()
    page = c.get("/datasets", "admin").text
    assert DATASET in page


def test_it_only_reads() -> None:
    c, sidecar = client()
    for name in widgets.WIDGETS:
        widget(c, name, "&query=EUR")
    c.get("/datasets", "admin")
    assert set(sidecar.read) <= {"ListDatasets", "ResolveIdentifier", "ResolveInstrument", "ListPrices"}


def test_the_csp_reaches_only_its_own_origin() -> None:
    c, _ = client()
    directives = dict(part.split(" ", 1) for part in CSP.split("; "))
    for name in ("connect-src", "img-src", "font-src"):
        assert "https:" not in directives[name] and "wss:" not in directives[name], name
    assert directives["connect-src"] == "'self'"
    assert "frame-ancestors" not in directives
    answer = call(c, "GET", "/app")
    assert dict(answer.headers)["content-security-policy"] == CSP


def test_the_runtime_config_turns_off_every_agent_surface_and_names_the_page() -> None:
    c, _ = client()
    text = call(c, "GET", "/config.js").text
    config = json.loads(re.search(r"= (\{.*\});", text, re.S).group(1))
    assert config["copilot"]["enabled"] is False
    assert config["ui"]["showCompanionMode"] is False
    assert config["data"]["allowHtmlJsExecution"] is False
    assert config["authentication"] == {"allowEmailLogin": False, "identityProviders": [], "sendUserEmailAsHeader": False}
    assert config["whiteLabel"]["name"] == "Open Meridian workspace"
    assert config["urls"] == {"backend": "/api", "ai": ""}
