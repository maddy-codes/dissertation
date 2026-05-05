"""Data preparation pipeline for dissertation fine-tuning and validation.

The functions in this module are deliberately side-effect light: credentials are
read from the caller/environment, raw Xero/working-paper JSON is transformed into
chat-style JSONL records, and optional Azure upload/Xero enrichment hooks are
kept separate from local transformation logic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ChatRecord:
    messages: list[dict[str, str]]


@dataclass(frozen=True)
class DatasetSplit:
    train_path: Path
    validation_path: Path
    train_count: int
    validation_count: int


SYSTEM_PROMPT = (
    "You are an expert UK accountant. Based on the provided Xero balance sheet "
    "and transaction analysis, generate the year-end working paper review notes."
)


def safe_decimal(value: Any) -> Decimal:
    """Convert a Xero value into Decimal without using binary float arithmetic."""
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def extract_company_name(blob_name: str) -> str:
    """Extract a readable company name from a stored working-paper filename."""
    filename = Path(blob_name).name
    filename = re.sub(r"^[A-Z][0-9]{4}_-_", "", filename)
    filename = re.sub(r"\.json$", "", filename, flags=re.IGNORECASE)
    parts = re.split(
        r"_Spreadsheets_|_Working_papers_|_Accounts_|_WP|_Year_end",
        filename,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    return parts[0].replace("_", " ").strip()


def format_money(value: Any) -> str:
    amount = safe_decimal(value)
    return f"GBP {amount:,.2f}"


def original_note_to_markdown(raw_json: dict[str, Any]) -> str:
    paragraphs = raw_json.get("original_json_data", {}).get("paragraphs", [])
    output: list[str] = []
    for paragraph in paragraphs:
        title = paragraph.get("paragraph_title", "").strip()
        content = "\n".join(str(item) for item in paragraph.get("content", []) if str(item).strip())
        if title or content:
            output.append(f"### {title}\n{content}".strip())
    return "\n\n".join(output).strip()


def balance_sheet_summary(raw_json: dict[str, Any]) -> str:
    rows = raw_json.get("xero_data", {}).get("balance_sheet", {}).get("Reports", [])
    lines = ["BALANCE SHEET SUMMARY:"]
    if not rows:
        return "BALANCE SHEET SUMMARY:\n- No balance sheet report available."
    for row in rows[0].get("Rows", []):
        if row.get("RowType") != "SummaryRow":
            continue
        cells = row.get("Cells", [])
        if len(cells) >= 2:
            lines.append(f"- {cells[0].get('Value', 'Unknown')}: {format_money(cells[1].get('Value'))}")
    return "\n".join(lines)


def analyze_xero_transactions(raw_json: dict[str, Any]) -> str:
    """Summarise subscriptions, outliers, and one-off payees from Xero transactions."""
    transactions = raw_json.get("xero_data", {}).get("bank_transactions", {}).get("BankTransactions", [])
    if not transactions:
        return "TRANSACTION ANALYSIS:\nNo transaction data available."

    normalised = []
    for transaction in transactions:
        contact = transaction.get("Contact")
        payee = contact.get("Name") if isinstance(contact, dict) else "Unknown Payee"
        amount = abs(safe_decimal(transaction.get("Total")))
        date_text = transaction.get("DateString") or transaction.get("Date") or "Unknown Date"
        normalised.append({"payee": payee, "amount": amount, "date": date_text})

    lines = ["TRANSACTION ANALYSIS:", "Subscriptions Detected:"]
    grouped: dict[tuple[str, Decimal], list[dict[str, Any]]] = {}
    for item in normalised:
        grouped.setdefault((item["payee"], item["amount"]), []).append(item)
    subscriptions = [(key, items) for key, items in grouped.items() if len(items) >= 3]
    if subscriptions:
        for (payee, amount), items in subscriptions:
            lines.append(f"- Found subscription: {payee} for {format_money(amount)} ({len(items)} times)")
    else:
        lines.append("- No recurring subscriptions detected.")

    lines.append("\nNew / One-Off Payees:")
    payee_counts: dict[str, int] = {}
    for item in normalised:
        payee_counts[item["payee"]] = payee_counts.get(item["payee"], 0) + 1
    one_offs = [item for item in normalised if payee_counts[item["payee"]] == 1]
    if one_offs:
        for item in one_offs[:30]:
            lines.append(f"- NEW PAYEE: {format_money(item['amount'])} paid to {item['payee']} on {item['date']}")
    else:
        lines.append("- No new/one-off payees detected.")
    return "\n".join(lines)


def build_user_context(raw_json: dict[str, Any]) -> str:
    metadata = raw_json.get("metadata", {})
    year_end = metadata.get("year_end_date", "Unknown")
    return "\n\n".join(
        [
            f"YEAR END DATE: {year_end}",
            balance_sheet_summary(raw_json),
            analyze_xero_transactions(raw_json),
        ]
    )


def process_xero_json(raw_json: dict[str, Any]) -> ChatRecord | None:
    assistant_response = original_note_to_markdown(raw_json)
    if not assistant_response:
        return None
    return ChatRecord(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Please draft the working papers based on this Xero data summary:\n\n{build_user_context(raw_json)}",
            },
            {"role": "assistant", "content": assistant_response},
        ]
    )


def iter_local_json_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            yield from sorted(path.glob("*.json"))
        elif path.suffix.lower() == ".json":
            yield path


def build_records_from_local(paths: Iterable[Path]) -> list[ChatRecord]:
    records: list[ChatRecord] = []
    for path in iter_local_json_files(paths):
        with path.open(encoding="utf-8") as handle:
            raw_json = json.load(handle)
        record = process_xero_json(raw_json)
        if record:
            records.append(record)
    return records


def write_jsonl(records: Iterable[ChatRecord], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps({"messages": record.messages}, ensure_ascii=False) + "\n")
            count += 1
    return count


def split_and_write(records: list[ChatRecord], output_dir: Path, validation_fraction: float = 0.15) -> DatasetSplit:
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    validation_count = max(1, round(len(records) * validation_fraction)) if records else 0
    train_records = records[:-validation_count] if validation_count else records
    validation_records = records[-validation_count:] if validation_count else []
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    train_path = output_dir / f"train_full_dataset_{stamp}.jsonl"
    validation_path = output_dir / f"validation_full_dataset_{stamp}.jsonl"
    return DatasetSplit(
        train_path=train_path,
        validation_path=validation_path,
        train_count=write_jsonl(train_records, train_path),
        validation_count=write_jsonl(validation_records, validation_path),
    )
