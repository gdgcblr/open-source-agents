"""Amount signals and the auto-apply decision.

The LLM supplies only a *name* confidence ("does this narration refer to this
client?"). Everything about amounts, TDS, ambiguity and the final decision is
computed here.
"""

from dataclasses import dataclass, field

EXACT, TDS, PARTIAL, OVER, MISMATCH = "EXACT", "TDS", "PARTIAL", "OVER", "MISMATCH"
AUTO_APPLIED, NEEDS_CONFIRMATION = "AUTO_APPLIED", "NEEDS_CONFIRMATION"


@dataclass(frozen=True)
class OpenInvoice:
    id: str
    client_id: str
    currency: str
    outstanding: int
    has_prior_payments: bool
    due_date: str


@dataclass
class Allocation:
    invoice_id: str
    paid: int
    tds: int


@dataclass
class AmountSignal:
    signal: str
    tds_rate: float | None = None
    allocations: list[Allocation] = field(default_factory=list)
    unallocated: int = 0


def _split_tds(inv: OpenInvoice, rate: float) -> Allocation:
    tds = round(inv.outstanding * rate)
    return Allocation(inv.id, inv.outstanding - tds, tds)


def amount_signal(amount: int, invoices: list[OpenInvoice], tds_rates: tuple[float, ...],
                  tolerance: int) -> AmountSignal:
    """How does `amount` relate to the outstanding total of `invoices`?"""
    total = sum(i.outstanding for i in invoices)
    if abs(amount - total) <= tolerance:
        return AmountSignal(EXACT, allocations=[Allocation(i.id, i.outstanding, 0) for i in invoices])

    # TDS is deducted from the invoice value, so only applies before any partial payment.
    if not any(i.has_prior_payments for i in invoices):
        for rate in tds_rates:
            allocs = [_split_tds(i, rate) for i in invoices]
            if abs(amount - sum(a.paid for a in allocs)) <= tolerance:
                return AmountSignal(TDS, tds_rate=rate, allocations=allocs)

    if len(invoices) > 1:
        return AmountSignal(MISMATCH)
    inv = invoices[0]
    if amount < total:
        return AmountSignal(PARTIAL, allocations=[Allocation(inv.id, amount, 0)])
    return AmountSignal(OVER, allocations=[Allocation(inv.id, inv.outstanding, 0)],
                        unallocated=amount - inv.outstanding)


def find_ambiguity(amount: int, proposed: list[OpenInvoice], others: list[OpenInvoice],
                   tds_rates: tuple[float, ...], tolerance: int) -> list[str]:
    """Other open invoices this payment could equally well settle.

    Same-client invoices that fall due *later* than the proposed one are not
    ambiguous: paying the oldest first is the safe convention (e.g. monthly
    retainers of the same amount).
    """
    proposed_clients = {i.client_id for i in proposed}
    oldest_due = min(i.due_date for i in proposed)
    ambiguous = []
    for other in others:
        if other.currency != proposed[0].currency:
            continue
        if amount_signal(amount, [other], tds_rates, tolerance).signal not in (EXACT, TDS):
            continue
        if other.client_id in proposed_clients and other.due_date >= oldest_due:
            continue
        ambiguous.append(other.id)
    return ambiguous


def decide(signal: str, name_confidence: float, invoice_count: int, ambiguous_with: list[str],
           min_confidence: float) -> str:
    if (invoice_count == 1 and signal in (EXACT, TDS) and not ambiguous_with
            and name_confidence >= min_confidence):
        return AUTO_APPLIED
    return NEEDS_CONFIRMATION
