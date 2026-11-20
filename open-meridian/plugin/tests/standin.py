"""A stand-in for the plugin's sidecar, answering the lake's and the master's
reads here: the euro's cash instrument priced in three currencies on one
business date, by one dataset the plugin is entitled to unless told not.
The SDK's recorder, which the plugin's role class is bound to."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import meridian
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.suites import Recorder

DATASET = "ecb:ecb_fx"
DAY_NS = 1_763_596_800_000_000_000  # 2025-11-20T00:00:00Z
CASH = {"EUR": "INS-EUR", "USD": "INS-USD", "GBP": "INS-GBP", "JPY": "INS-JPY"}
RATES = {"USD": "1.1225", "GBP": "0.8712", "JPY": "171.43"}


def wire(text: str) -> ops.Decimal:
    amount = Decimal(text)
    scale = max(0, -int(amount.as_tuple().exponent))
    return ops.Decimal(low=int(amount.scaleb(scale)), scale=scale)


class _Named:
    def __getattr__(self, name: str) -> str:
        return name


class Sidecar(Recorder):
    identity = meridian.Identity("workspace", roles=("reporting",))
    grants = meridian.Grants()

    def __init__(
        self, entitled: bool = True, alive_ns: int = DAY_NS, listed: bool = True
    ) -> None:
        super().__init__("workspace")
        self.entitled = entitled
        #: Whether ListDatasets names the dataset at all. A deployment's
        #: sidecar names only what the plugin is entitled to: with the one
        #: entitlement withdrawn, it names none.
        self.listed = listed
        self.alive_ns = alive_ns
        self.read: list[str] = []

    def _operations(self) -> Any:
        return _Named()

    async def _operate(self, method: Any, params: Any) -> Any:
        self.read.append(cast(str, method))
        if method == "ListDatasets":
            if not self.listed:
                return ops.ListDatasetsResult()
            return ops.ListDatasetsResult(
                datasets=[
                    ops.DatasetRef(
                        dataset=DATASET,
                        vendor="European Central Bank",
                        liveness=[ops.DatasetLiveness(dataset=DATASET, alive_at_ns=self.alive_ns)],
                    )
                ],
                entitlements=[ops.DatasetEntitlement(dataset=DATASET, allowed=self.entitled)],
            )
        if method == "ResolveIdentifier":
            code = params.identifiers[0].value
            if params.identifiers[0].scheme == "iso4217" and code in CASH:
                return ops.ResolveIdentifierResult(found=True, instrument_id=CASH[code])
            return ops.ResolveIdentifierResult(found=False)
        if method == "ResolveInstrument":
            codes = {v: k for k, v in CASH.items()}
            code = codes.get(params.instrument_id)
            if code is None:
                return ops.ResolveInstrumentResult(found=False)
            return ops.ResolveInstrumentResult(
                found=True,
                instrument=ops.InstrumentRecord(
                    instrument_id=params.instrument_id,
                    identifiers=[ops.Identifier(scheme="iso4217", value=code)],
                    asset_class=ops.ASSET_CLASS_CASH,
                    currency=code,
                    description=f"{code} cash",
                ),
            )
        if method == "ListPrices":
            if not self.entitled:
                return ops.ListPricesResult(
                    unanswered=[
                        ops.Unanswered(dataset=DATASET, reason=ops.UNANSWERED_REASON_NOT_ENTITLED)
                    ]
                )
            return ops.ListPricesResult(
                prices=[
                    ops.Price(
                        meta=ops.ObservationMeta(
                            subjects=[ops.SubjectRef(entity_id=CASH["EUR"])],
                            source=ops.Source(dataset=DATASET),
                            valid_from_ns=DAY_NS + 15 * 3600 * 1_000_000_000,
                            recorded_at_ns=DAY_NS + 16 * 3600 * 1_000_000_000,
                            business_date="2025-11-20",
                        ),
                        kind=ops.PRICE_KIND_CLOSE,
                        price=ops.Money(amount=wire(rate), instrument_id=CASH[code]),
                    )
                    for code, rate in RATES.items()
                ]
            )
        raise AssertionError(f"the workspace read {method}, which no stand-in here answers")
