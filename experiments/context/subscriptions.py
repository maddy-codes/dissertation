from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

from experiments.types import Example, SubscriptionPolicy
from experiments.utils import safe_float


def summarise_subscriptions(example: Example, policy: SubscriptionPolicy) -> str:
    """
    Subscription / recurring payments summary.

    Heuristic:
    - Group by contact name.
    - Within a contact, cluster by amount (within tolerance).
    - Flag clusters with >= min_occurrences.
    """
    txs = example.transactions
    if not txs:
        return "SUBSCRIPTIONS_SUMMARY (no transactions found)"

    by_contact: Dict[str, list[dict]] = defaultdict(list)
    for t in txs:
        by_contact[_contact_name(t)].append(t)

    recurring: list[str] = []
    for contact, items in by_contact.items():
        clusters = _cluster_by_amount(items, policy.amount_tolerance_gbp)
        for amount, cluster in clusters:
            if len(cluster) < policy.min_occurrences:
                continue
            dates = sorted([_coerce_date(t) for t in cluster if _coerce_date(t)])
            total_abs = sum(abs(safe_float(t.get("Total")) or 0.0) for t in cluster)
            recurring.append(
                f"- {contact}: ~£{amount:,.2f} x{len(cluster)} total_abs=£{total_abs:,.2f} first={dates[0] if dates else ''} last={dates[-1] if dates else ''}"
            )

    recurring.sort()
    if not recurring:
        return "SUBSCRIPTIONS_SUMMARY none_detected"
    return "\n".join(["SUBSCRIPTIONS_SUMMARY detected:", *recurring[:30]])


def _contact_name(t: dict) -> str:
    c = t.get("Contact")
    if isinstance(c, dict) and isinstance(c.get("Name"), str) and c["Name"].strip():
        return c["Name"].strip()
    return "UNKNOWN_CONTACT"


def _coerce_date(t: dict) -> str | None:
    # Accept either ISO date or Xero "/Date(ms+0000)/"
    ds = t.get("DateString")
    if isinstance(ds, str) and ds:
        return ds[:10]
    d = t.get("Date")
    if isinstance(d, str) and d.startswith("/Date("):
        try:
            ms = int(d.split("(")[1].split("+")[0].split(")")[0])
            return datetime.utcfromtimestamp(ms / 1000.0).strftime("%Y-%m-%d")
        except Exception:
            return None
    if isinstance(d, str) and len(d) >= 10:
        return d[:10]
    return None


def _cluster_by_amount(items: list[dict], tol: float) -> list[tuple[float, list[dict]]]:
    clusters: list[tuple[float, list[dict]]] = []
    for t in items:
        amt = safe_float(t.get("Total"))
        if amt is None:
            continue
        amt = abs(amt)
        placed = False
        for i, (center, members) in enumerate(clusters):
            if abs(center - amt) <= tol:
                members.append(t)
                # update center as running average
                new_center = (center * (len(members) - 1) + amt) / len(members)
                clusters[i] = (new_center, members)
                placed = True
                break
        if not placed:
            clusters.append((amt, [t]))
    clusters.sort(key=lambda kv: (len(kv[1]), kv[0]), reverse=True)
    return clusters

