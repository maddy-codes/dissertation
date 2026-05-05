"""Context builders for prompt-engineering and fine-tuning experiments."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from experiments.types import Example, MaterialityPolicy, SubscriptionPolicy


def _amount(transaction: dict) -> float:
    try:
        return abs(float(transaction.get("Total", 0)))
    except (TypeError, ValueError):
        return 0.0


def _payee(transaction: dict) -> str:
    contact = transaction.get("Contact")
    if isinstance(contact, dict):
        return str(contact.get("Name") or "Unknown Payee")
    return "Unknown Payee"


def _raw_context(transactions: Iterable[dict], fraction: float) -> str:
    transactions = list(transactions)
    count = max(1, round(len(transactions) * fraction)) if transactions else 0
    selected = transactions[:count]
    lines = ["RAW TRANSACTION CONTEXT:"]
    for transaction in selected:
        lines.append(f"- {_payee(transaction)}: GBP {_amount(transaction):.2f}")
    return "\n".join(lines)


def _materiality_subscription_context(
    example: Example,
    materiality_policy: MaterialityPolicy,
    subscription_policy: SubscriptionPolicy,
) -> str:
    transactions = example.transactions
    total = sum(_amount(transaction) for transaction in transactions)
    threshold = total * materiality_policy.relative_fraction
    payee_counts = Counter(_payee(transaction) for transaction in transactions)

    lines = ["MATERIALITY AND SUBSCRIPTION CONTEXT:"]
    lines.append(f"- Materiality threshold: GBP {threshold:.2f}")
    for transaction in transactions:
        amount = _amount(transaction)
        if amount >= threshold:
            lines.append(f"- Material item: {_payee(transaction)} GBP {amount:.2f}")
    for payee, count in payee_counts.items():
        if count >= subscription_policy.min_occurrences:
            lines.append(f"- Recurring payee: {payee} ({count} occurrences)")
    return "\n".join(lines)


def build_context_variants(
    example: Example,
    requested_modes: list[str],
    materiality_policy: MaterialityPolicy,
    subscription_policy: SubscriptionPolicy,
) -> dict[str, str]:
    variants: dict[str, str] = {}
    if "raw" in requested_modes:
        variants["raw_25"] = _raw_context(example.transactions, 0.25)
        variants["raw_50"] = _raw_context(example.transactions, 0.50)
        variants["raw_100"] = _raw_context(example.transactions, 1.00)
    if "materiality+subscriptions" in requested_modes:
        variants["materiality+subscriptions"] = _materiality_subscription_context(
            example,
            materiality_policy,
            subscription_policy,
        )
    return variants
