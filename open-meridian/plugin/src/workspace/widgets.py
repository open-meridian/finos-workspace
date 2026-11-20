"""The one built-in connection: Workspace's widget backend, answered in process.

Workspace asks a connection for its `widgets.json` and `apps.json`, and each
widget for its data, through `/app/data-connectors/api-source/{id}/request`.
Here that connection is the lake, through the plugin's sidecar: no request
leaves the process. The connection's address names no host that resolves
(`.invalid`), so a browser that tried to call it directly would reach
nothing; the Content-Security-Policy refuses it first.

The widgets are Workspace's built-in `html` type, drawn here with no script
(ALLOW_HTML_JS_EXECUTION is off), each also answering its rows (`raw=true`)
so the rows button shows what the view shows. Field names describe
themselves, numbers are numbers and times are ISO 8601.
"""

from __future__ import annotations

import html
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .lake import Lake, Refused, now_ns

#: The connection, as Workspace lists it.
SOURCE_ID = "open-meridian-lake"
SOURCE_NAME = "Open Meridian lake"
SOURCE_URL = "http://lake.meridian.invalid"

CATEGORY = "Open Meridian"
LOOKUP_PARAM = {
    "paramName": "query",
    "type": "text",
    "label": "Identifier",
    "description": "An ISO 4217 code or a pair of them (EUR/USD), a FIGI, an ISIN, a ticker, or an instrument's ID",
    "value": "EUR/USD",
}

WIDGETS: dict[str, dict[str, Any]] = {
    "fx_rates_table": {
        "name": "Latest FX reference rates",
        "description": "The latest reference rate of the euro in each currency the lake holds, with its business date, its time and the dataset it came from",
        "category": CATEGORY,
        "subCategory": "FX",
        "type": "html",
        "endpoint": "fx_rates_table",
        "gridData": {"w": 20, "h": 14},
        "source": "The deployment's lake",
        "raw": True,
    },
    "fx_rates_chart": {
        "name": "FX reference rates, chart",
        "description": "The latest reference rates of the euro as bars, each against the currency it is quoted in, with the business date and the dataset",
        "category": CATEGORY,
        "subCategory": "FX",
        "type": "html",
        "endpoint": "fx_rates_chart",
        "gridData": {"w": 20, "h": 14},
        "source": "The deployment's lake",
        "raw": True,
    },
    "dataset_ages": {
        "name": "Dataset ages",
        "description": "Each dataset this workspace may read: whether it is entitled, when its source was last heard and how long ago",
        "category": CATEGORY,
        "subCategory": "Data",
        "type": "html",
        "endpoint": "dataset_ages",
        "gridData": {"w": 20, "h": 10},
        "source": "The deployment's lake",
        "raw": True,
    },
    "instrument_lookup": {
        "name": "Instrument lookup",
        "description": "The deployment's master records for an identifier: an ISO 4217 code or a pair, a FIGI, an ISIN, a ticker or an instrument's ID",
        "category": CATEGORY,
        "subCategory": "Master",
        "type": "html",
        "endpoint": "instrument_lookup",
        "gridData": {"w": 20, "h": 10},
        "source": "The deployment's master",
        "raw": True,
        "params": [LOOKUP_PARAM],
    },
}

APPS = json.loads((Path(__file__).parent / "apps.json").read_text())

#: The kit, as the dashboard serves it on the plugin's own host: the widget's
#: view is drawn in the person's theme with the kit's tokens.
KIT = "/.meridian/ui/0.16.0/"


def _page(theme: str, body: str) -> str:
    mode = "light" if theme == "light" else "dark"
    return (
        f"<!doctype html><html data-om-mode='{mode}'><head><meta charset='utf-8'>"
        f"<link rel='stylesheet' href='{KIT}meridian.css'><style>"
        "body{margin:0;padding:8px;background:var(--card);color:var(--ink)}"
        "table{border-collapse:collapse;width:100%}th,td{padding:4px 6px;border-bottom:1px solid var(--line);"
        "text-align:left;overflow-wrap:anywhere}th{color:var(--ink-soft)}td.n{text-align:right;"
        "font-variant-numeric:tabular-nums}p{margin:4px 0}.muted{color:var(--ink-soft)}"
        ".refused{color:var(--warn-ink)}svg text{fill:var(--ink);font-size:11px}"
        "</style></head><body>" + body + "</body></html>"
    )


def _table(columns: list[tuple[str, str]], rows: list[dict[str, Any]]) -> str:
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    lines = []
    for row in rows:
        cells = []
        for key, _ in columns:
            value = row.get(key)
            number = isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
            text = "" if value is None else str(value)
            cells.append(f"<td{' class=n' if number else ''}>{html.escape(text)}</td>")
        lines.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(lines)}</tbody></table>"


def _refused(theme: str, why: str) -> str:
    return _page(theme, f"<p class='refused' data-refused>Refused: {html.escape(why)}</p>")


def _empty(theme: str, what: str) -> str:
    return _page(theme, f"<p class='muted' data-empty>{html.escape(what)}</p>")


def _declined(query: dict[str, str], why: str) -> tuple[int, str, bytes]:
    """A refusal: its words in the view, and as the rows' error."""
    if query.get("raw") == "true":
        return 403, "application/json", json.dumps({"detail": f"Refused: {why}"}).encode()
    return _html(_refused(query.get("theme", "dark"), why))


def _json(rows: Any) -> tuple[int, str, bytes]:
    def plain(value: Any) -> Any:
        return float(value) if isinstance(value, Decimal) else value

    data = [{key: plain(value) for key, value in row.items()} for row in rows]
    return 200, "application/json", json.dumps(data).encode()


def _html(text: str) -> tuple[int, str, bytes]:
    return 200, "text/html; charset=utf-8", text.encode()


async def fx_rates_table(lake: Lake, query: dict[str, str]) -> tuple[int, str, bytes]:
    theme = query.get("theme", "dark")
    try:
        rates = await lake.rates()
    except Refused as why:
        return _declined(query, str(why))
    rows = [asdict(rate) for rate in rates]
    if query.get("raw") == "true":
        return _json(rows)
    if not rows:
        return _html(_empty(theme, "The lake holds no reference rate yet."))
    columns = [
        ("pair", "Pair"),
        ("rate", "Rate"),
        ("business_date", "Business date"),
        ("valid_from", "Time"),
        ("dataset", "Source"),
    ]
    return _html(_page(theme, _table(columns, rows)))


async def fx_rates_chart(lake: Lake, query: dict[str, str]) -> tuple[int, str, bytes]:
    theme = query.get("theme", "dark")
    try:
        rates = await lake.rates()
    except Refused as why:
        return _declined(query, str(why))
    rows = [asdict(rate) for rate in rates]
    if query.get("raw") == "true":
        return _json(rows)
    if not rows:
        return _html(_empty(theme, "The lake holds no reference rate yet."))
    # One bar a currency, on a log scale: the rates run from under one to
    # thousands, so a linear axis would show one bar.
    width, row_height, label, gap = 420, 18, 70, 4
    logs = [math.log10(float(rate.rate)) for rate in rates]
    low, high = min(min(logs), 0.0) - 0.2, max(logs) + 0.2
    bars = []
    for n, (rate, value) in enumerate(zip(rates, logs, strict=True)):
        y = n * (row_height + gap)
        length = max(2.0, (value - low) / (high - low) * (width - label - 80))
        bars.append(
            f"<text x='0' y='{y + 13}'>{html.escape(rate.pair)}</text>"
            f"<rect x='{label}' y='{y}' width='{length:.1f}' height='{row_height}' fill='var(--accent)'/>"
            f"<text x='{label + length + 4:.1f}' y='{y + 13}'>{html.escape(str(rate.rate))}</text>"
        )
    height = len(rates) * (row_height + gap)
    dates = sorted({rate.business_date for rate in rates})
    sources = sorted({rate.dataset for rate in rates})
    caption = (
        f"<p class='muted'>Business date {html.escape(', '.join(dates))} · "
        f"{html.escape(', '.join(sources))} · log scale</p>"
    )
    svg = (
        f"<svg role='img' aria-label='Reference rates of the euro' viewBox='0 0 {width} {height}' "
        f"width='100%' preserveAspectRatio='xMinYMin meet'>{''.join(bars)}</svg>"
    )
    return _html(_page(theme, caption + svg))


async def dataset_ages(lake: Lake, query: dict[str, str]) -> tuple[int, str, bytes]:
    theme = query.get("theme", "dark")
    try:
        ages = await lake.ages(now_ns())
    except Refused as why:
        return _declined(query, str(why))
    rows = [asdict(age) for age in ages]
    if query.get("raw") == "true":
        return _json(rows)
    if not rows:
        return _html(_empty(theme, "No dataset is licensed to this workspace yet."))
    shown = [
        {
            **row,
            "entitled": "Entitled" if row["entitled"] else "Not entitled",
            "alive_at": row["alive_at"] or "Not heard yet",
        }
        for row in rows
    ]
    columns = [
        ("dataset", "Dataset"),
        ("vendor", "Vendor"),
        ("entitled", "Entitlement"),
        ("alive_at", "Last heard"),
        ("age_seconds", "Age (s)"),
        ("stale_after_seconds", "Stale after (s)"),
    ]
    return _html(_page(theme, _table(columns, shown)))


async def instrument_lookup(lake: Lake, query: dict[str, str]) -> tuple[int, str, bytes]:
    theme = query.get("theme", "dark")
    asked = query.get("query", "")
    try:
        found = await lake.lookup(asked)
    except Refused as why:
        return _declined(query, str(why))
    rows = [{**asdict(each), "identifiers": ", ".join(each.identifiers)} for each in found]
    if query.get("raw") == "true":
        return _json(rows)
    if not rows:
        return _html(_empty(theme, f"The master holds no instrument for {asked!r}."))
    columns = [
        ("asked", "Asked"),
        ("instrument_id", "Instrument"),
        ("description", "Description"),
        ("asset_class", "Asset class"),
        ("currency", "Currency"),
        ("identifiers", "Identifiers"),
    ]
    return _html(_page(theme, _table(columns, rows)))


Endpoint = Callable[[Lake, dict[str, str]], Awaitable[tuple[int, str, bytes]]]

ENDPOINTS: dict[str, Endpoint] = {
    "fx_rates_table": fx_rates_table,
    "fx_rates_chart": fx_rates_chart,
    "dataset_ages": dataset_ages,
    "instrument_lookup": instrument_lookup,
}


def source() -> dict[str, Any]:
    """The connection as `/app/data-connectors/api-source` lists it."""
    return {
        "id": SOURCE_ID,
        "uuid": SOURCE_ID,
        "name": SOURCE_NAME,
        "url": SOURCE_URL,
        "endpointHeaders": [],
        "isEntityBackend": True,
        "hasApiKey": False,
        "mcpServers": [],
    }


async def request(lake: Lake, url: str) -> tuple[int, str, bytes]:
    """A widget request to the connection, by the URL the front end built."""
    parts = urlsplit(url)
    if f"{parts.scheme}://{parts.netloc}" != SOURCE_URL:
        return 403, "application/json", b'{"detail":"This workspace reads only the lake."}'
    path = parts.path.strip("/")
    query = {key: values[-1] for key, values in parse_qs(parts.query).items()}
    if path == "widgets.json":
        return 200, "application/json", json.dumps(WIDGETS).encode()
    if path == "apps.json":
        return 200, "application/json", json.dumps(APPS).encode()
    endpoint = ENDPOINTS.get(path)
    if endpoint is None:
        return 404, "application/json", b'{"detail":"No such widget."}'
    return await endpoint(lake, query)
