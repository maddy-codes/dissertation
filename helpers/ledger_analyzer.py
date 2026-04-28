"""
Ledger analyser for a single nominal account.

Identifies recurring subscriptions, year-on-year new vendors, large items,
and value spikes/drops. Sign convention is preserved: amounts are kept signed
so the analyst can see whether an unusual movement is a charge or a credit.
"""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _description_key(tx: Dict[str, Any]) -> str:
    desc = (tx.get("Description") or "").strip()
    return desc if desc else "Unknown"


def _classify_cadence(dates: List[date]) -> Optional[str]:
    """Return a human cadence label if the gaps look regular."""
    if len(dates) < 3:
        return None
    sorted_dates = sorted(dates)
    gaps_days = [
        (sorted_dates[i + 1] - sorted_dates[i]).days
        for i in range(len(sorted_dates) - 1)
    ]
    if not gaps_days:
        return None
    avg_gap = sum(gaps_days) / len(gaps_days)
    if avg_gap <= 0:
        return None
    # Coefficient of variation - tighter means more regular cadence
    try:
        stdev = statistics.pstdev(gaps_days)
    except statistics.StatisticsError:
        stdev = 0
    cv = stdev / avg_gap if avg_gap else 0

    if cv > 0.5:
        return None  # Too irregular to call a subscription

    if 25 <= avg_gap <= 35:
        return "Monthly"
    if 6 <= avg_gap <= 8:
        return "Weekly"
    if 13 <= avg_gap <= 16:
        return "Fortnightly"
    if 85 <= avg_gap <= 100:
        return "Quarterly"
    if 350 <= avg_gap <= 380:
        return "Annual"
    return f"Approx. every {int(round(avg_gap))} days"


def analyze_ledger(
    current_txs: List[Dict[str, Any]], prior_txs: List[Dict[str, Any]]
) -> str:
    """
    Build a textual ledger summary for one nominal.

    Each tx is expected to have: Description, Amount (signed float), Date (YYYY-MM-DD).
    """
    if not current_txs and not prior_txs:
        return "No transactions found for this account."

    # Group by description for both years
    curr_by_key: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tx in current_txs:
        try:
            amt = float(tx.get("Amount", 0))
        except (TypeError, ValueError):
            amt = 0.0
        if amt == 0:
            continue
        curr_by_key[_description_key(tx)].append(
            {"Amount": amt, "Date": tx.get("Date", ""), "Source": tx.get("Source", "")}
        )

    prior_by_key: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tx in prior_txs:
        try:
            amt = float(tx.get("Amount", 0))
        except (TypeError, ValueError):
            amt = 0.0
        if amt == 0:
            continue
        prior_by_key[_description_key(tx)].append(
            {"Amount": amt, "Date": tx.get("Date", ""), "Source": tx.get("Source", "")}
        )

    # Determine the dominant sign for the account from current-year totals
    # (positive => debit-side account, negative => credit-side / income)
    current_total = sum(t["Amount"] for items in curr_by_key.values() for t in items)
    account_sign = 1 if current_total >= 0 else -1

    def _direction_word(amt: float) -> Tuple[str, str]:
        """Return (direction_label, polarity_label) given account sign."""
        # Polarity: same sign as the account's normal direction is "as expected"
        if amt * account_sign >= 0:
            return ("Charge" if account_sign >= 0 else "Receipt", "in line with account")
        return ("Refund" if account_sign >= 0 else "Reversal", "opposite to normal direction")

    # 1. Top 5 largest items in current year (by absolute value)
    sorted_curr = sorted(
        (t for items in curr_by_key.values() for t in items),
        key=lambda x: abs(x["Amount"]),
        reverse=True,
    )
    top_5 = []
    for tx in sorted_curr[:5]:
        # find the description for this tx
        desc = "Unknown"
        for k, items in curr_by_key.items():
            if tx in items:
                desc = k
                break
        top_5.append((desc, tx["Amount"], tx["Date"]))

    # 2. New descriptions/vendors not present in prior year
    new_items: List[Tuple[str, float, int]] = []
    for key, items in curr_by_key.items():
        if key == "Unknown" or key in prior_by_key:
            continue
        total = sum(t["Amount"] for t in items)
        new_items.append((key, total, len(items)))
    new_items.sort(key=lambda x: abs(x[1]), reverse=True)

    # 3. Stopped vendors (in prior year, not in current)
    stopped_items: List[Tuple[str, float]] = []
    for key, items in prior_by_key.items():
        if key == "Unknown" or key in curr_by_key:
            continue
        total = sum(t["Amount"] for t in items)
        stopped_items.append((key, total))
    stopped_items.sort(key=lambda x: abs(x[1]), reverse=True)

    # 4. Recurring subscriptions and anomalies (spike/drop vs historical mean)
    subscriptions: List[str] = []
    anomalies: List[str] = []

    for key in set(curr_by_key.keys()).union(prior_by_key.keys()):
        if key == "Unknown":
            continue
        all_txs = prior_by_key.get(key, []) + curr_by_key.get(key, [])
        if len(all_txs) < 3:
            continue

        amounts = [t["Amount"] for t in all_txs]
        dates = [d for d in (_parse_date(t["Date"]) for t in all_txs) if d]
        cadence = _classify_cadence(dates)

        # Use absolute values for the "is it a regular size" check, but keep sign for reporting
        abs_amounts = [abs(a) for a in amounts]
        try:
            mean_abs = statistics.fmean(abs_amounts)
            std_abs = statistics.pstdev(abs_amounts)
        except statistics.StatisticsError:
            mean_abs = sum(abs_amounts) / len(abs_amounts) if abs_amounts else 0
            std_abs = 0

        if cadence:
            curr_items = curr_by_key.get(key, [])
            curr_count = len(curr_items)
            curr_total = sum(t["Amount"] for t in curr_items) if curr_items else 0
            subscriptions.append(
                f"- {key}: {cadence} cadence, {curr_count} payments this year, "
                f"avg £{mean_abs:,.2f}, total £{curr_total:,.2f}"
            )

        # Spike/drop detection on signed amounts vs absolute mean
        if std_abs > 0:
            upper = mean_abs + 2 * std_abs
            lower = max(0, mean_abs - 2 * std_abs)
            for tx in curr_by_key.get(key, []):
                a = abs(tx["Amount"])
                if a > upper or a < lower:
                    direction = "Spike" if a > upper else "Drop"
                    label, polarity = _direction_word(tx["Amount"])
                    anomalies.append(
                        f"- {key}: {direction} to £{tx['Amount']:,.2f} on "
                        f"{tx['Date']} ({label}, {polarity}; historical mean £{mean_abs:,.2f})"
                    )

    lines: List[str] = []

    if subscriptions:
        lines.append("=== RECURRING ITEMS ===")
        lines.extend(subscriptions[:15])
        lines.append("")

    if new_items:
        lines.append("=== NEW DESCRIPTIONS / VENDORS THIS YEAR ===")
        for key, total, count in new_items[:10]:
            lines.append(f"- {key}: £{total:,.2f} across {count} transaction(s)")
        lines.append("")

    if stopped_items:
        lines.append("=== STOPPED DESCRIPTIONS / VENDORS (present last year, absent this year) ===")
        for key, total in stopped_items[:10]:
            lines.append(f"- {key}: £{total:,.2f} last year")
        lines.append("")

    if top_5:
        lines.append("=== TOP 5 LARGEST ITEMS THIS YEAR ===")
        for desc, amount, dt in top_5:
            lines.append(f"- {desc}: £{amount:,.2f} on {dt or 'Unknown date'}")
        lines.append("")

    if anomalies:
        lines.append("=== UNUSUAL MOVEMENTS (>2 SD from historical mean) ===")
        lines.extend(anomalies[:10])
        lines.append("")

    if not lines:
        return "No notable transactional patterns identified."

    return "\n".join(lines).strip()
