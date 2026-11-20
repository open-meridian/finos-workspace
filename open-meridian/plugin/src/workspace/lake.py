"""The plugin's reads: its `reporting` role class, and what each widget asks.

Every read goes through the plugin's sidecar, at the plugin's entitlements,
and records nothing. A read the lake declines is said as a refusal, with its
reason, never shown as an empty table.

The reads are the reporting role's that exist today (SDK 0.37.1):

- the latest reference rates: `resolve_identifier` for the euro's cash
  instrument by its ISO 4217 code, then `list_prices` for its closes, the
  latest in force, each quoted in another currency's cash instrument;
- the datasets' ages: `list_datasets`, each dataset's liveness and
  entitlement;
- the instrument lookup: `resolve_identifier` by an identifier and
  `resolve_instrument` for the record. The role has no text search over the
  master; the lookup takes an identifier (a code, a pair, a FIGI, an ISIN, a
  ticker or an instrument's ID).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import meridian
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import reporting

log = logging.getLogger("workspace")

NS = 1_000_000_000

#: The currency whose cash instrument the reference rates price.
BASE = "EUR"

REASONS = {
    ops.UNANSWERED_REASON_NOT_ENTITLED: "not entitled",
    ops.UNANSWERED_REASON_NOT_COVERED: "not covered by any dataset",
    ops.UNANSWERED_REASON_ASKED_SOURCE: "asked of its source, not answered yet",
    ops.UNANSWERED_REASON_SOURCE_SILENT: "its source states nothing for it",
    ops.UNANSWERED_REASON_UNRESOLVED: "its instrument is not resolved",
    ops.UNANSWERED_REASON_BEYOND_HISTORY: "beyond the dataset's history",
    ops.UNANSWERED_REASON_NOT_KEPT: "not kept",
    ops.UNANSWERED_REASON_QUARANTINED: "quarantined",
}


class Refused(Exception):
    """A read the deployment declined, said as it was declined."""


def moment(ns: int) -> str:
    """A time in nanoseconds as ISO 8601, in UTC; empty for none."""
    if not ns:
        return ""
    return datetime.fromtimestamp(ns / NS, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Rate:
    """One reference rate: the euro in `currency`, as the source quotes it."""

    pair: str
    currency: str
    rate: Decimal
    business_date: str
    valid_from: str
    recorded_at: str
    dataset: str


@dataclass(frozen=True)
class Age:
    """One dataset this plugin may read, and how old what it holds is."""

    dataset: str
    vendor: str
    entitled: bool
    alive_at: str
    age_seconds: int | None
    stale_after_seconds: int | None
    newest_row: str


@dataclass(frozen=True)
class Found:
    """One instrument the master holds for a lookup."""

    asked: str
    instrument_id: str
    description: str
    asset_class: str
    currency: str
    identifiers: list[str] = field(default_factory=list)


def _asset_class(value: int) -> str:
    name = ops.AssetClass.Name(value) if value else "ASSET_CLASS_UNSPECIFIED"
    return name.removeprefix("ASSET_CLASS_").replace("_", " ").lower()


@dataclass(eq=False)
class Lake(reporting.Role):
    """The plugin's reporting role class: reads only, nothing heard."""

    #: The ISO 4217 code of each cash instrument read, by its ID: master
    #: records, not anybody's data, held while the process runs.
    codes: dict[str, str] = field(default_factory=dict)

    async def instrument_of(self, scheme: str, value: str) -> str:
        """The instrument the master holds for one identifier, or ""."""
        found = await self.resolve_identifier(
            identifiers=[meridian.Identifier(scheme=scheme, value=value)]
        )
        return str(found.instrument_id) if found.found else ""

    async def code_of(self, instrument_id: str) -> str:
        """A cash instrument's ISO 4217 code, read from the master once."""
        if instrument_id not in self.codes:
            record = await self.resolve_instrument(instrument_id=instrument_id)
            codes = [
                each.value
                for each in record.instrument.identifiers
                if record.found and each.scheme == "iso4217"
            ]
            self.codes[instrument_id] = codes[0] if codes else instrument_id
        return self.codes[instrument_id]

    async def entitlement_refusal(self) -> str:
        """Why the plugin reads no dataset, or "" when it is entitled to one."""
        read = await self.list_datasets()
        allowed = {each.dataset for each in read.entitlements if each.allowed}
        names = [each.dataset for each in read.datasets]
        if allowed & set(names):
            return ""
        if not names:
            return "No dataset is licensed to this plugin yet."
        return (
            "This plugin is not entitled to "
            + ", ".join(sorted(names))
            + ": a deployment admin entitles it on Data sources."
        )

    async def rates(self) -> list[Rate]:
        """The latest reference rate of the euro in each currency the lake
        holds one for, by the deployment's source priority."""
        why = await self.entitlement_refusal()
        if why:
            raise Refused(why)
        euro = await self.instrument_of("iso4217", BASE)
        if not euro:
            raise Refused(f"The deployment's master holds no cash instrument for {BASE}.")
        out: list[Rate] = []
        unanswered: list[str] = []
        cursor = ""
        while True:
            page = await self.list_prices(
                subjects=[meridian.SubjectRef(entity_id=euro)],
                kinds=["close"],
                cursor=cursor,
            )
            for each in page.unanswered:
                unanswered.append(
                    f"{each.dataset or 'the lake'}: {REASONS.get(each.reason, 'not answered')}"
                )
            for price in page.prices:
                money = price.price
                code = money.currency_code or await self.code_of(money.instrument_id)
                out.append(
                    Rate(
                        pair=f"{BASE}/{code}",
                        currency=code,
                        rate=meridian.as_decimal(money.amount),
                        business_date=price.meta.business_date,
                        valid_from=moment(price.meta.valid_from_ns),
                        recorded_at=moment(price.meta.recorded_at_ns),
                        dataset=price.meta.source.dataset,
                    )
                )
            cursor = page.next_cursor
            if not cursor:
                break
        if not out and unanswered:
            raise Refused("The lake did not answer: " + "; ".join(sorted(set(unanswered))) + ".")
        return sorted(out, key=lambda rate: rate.currency)

    async def ages(self, now_ns: int) -> list[Age]:
        """Each dataset this plugin may read: whether it is entitled, when
        its source was last heard alive, and how long ago."""
        read = await self.list_datasets()
        allowed = {each.dataset: each.allowed for each in read.entitlements}
        out = []
        for ref in read.datasets:
            alive = max((each.alive_at_ns for each in ref.liveness), default=0)
            out.append(
                Age(
                    dataset=ref.dataset,
                    vendor=ref.vendor or ref.declaration.vendor,
                    entitled=allowed.get(ref.dataset, False),
                    alive_at=moment(alive),
                    age_seconds=(now_ns - alive) // NS if alive else None,
                    stale_after_seconds=ref.stale_after_ns // NS if ref.stale_after_ns else None,
                    newest_row="",
                )
            )
        return sorted(out, key=lambda age: age.dataset)

    async def lookup(self, query: str) -> list[Found]:
        """The master's records for an identifier: an ISO 4217 code or a
        pair of them (EUR/USD), a FIGI, an ISIN, an instrument's ID, or a
        ticker."""
        asked = query.strip()
        if not asked:
            return []
        pair = re.fullmatch(r"([A-Za-z]{3})\s*[/ ]?\s*([A-Za-z]{3})", asked)
        if pair and len(asked.replace("/", "").replace(" ", "")) == 6:
            tries = [("iso4217", pair.group(1).upper()), ("iso4217", pair.group(2).upper())]
        elif re.fullmatch(r"[A-Za-z]{3}", asked):
            tries = [("iso4217", asked.upper())]
        elif re.fullmatch(r"(INS|LCL)-[0-9A-Z]+", asked.upper()):
            tries = [("id", asked.upper())]
        elif re.fullmatch(r"BBG[0-9A-Z]{9}", asked.upper()):
            tries = [("figi", asked.upper())]
        elif re.fullmatch(r"[A-Z]{2}[0-9A-Z]{9}[0-9]", asked.upper()):
            tries = [("isin", asked.upper())]
        else:
            tries = [("ticker", asked.upper())]
        found: list[Found] = []
        for scheme, value in tries:
            instrument = value if scheme == "id" else await self.instrument_of(scheme, value)
            if not instrument:
                continue
            record = await self.resolve_instrument(instrument_id=instrument)
            if not record.found:
                continue
            held = record.instrument
            found.append(
                Found(
                    asked=value,
                    instrument_id=held.instrument_id,
                    description=held.description,
                    asset_class=_asset_class(held.asset_class),
                    currency=held.currency,
                    identifiers=[f"{each.scheme}:{each.value}" for each in held.identifiers],
                )
            )
        return found


def now_ns() -> int:
    return int(datetime.now(UTC).timestamp() * NS)
