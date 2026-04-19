from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(data: Any) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def safe_float(val: Any) -> float | None:
    try:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            cleaned = val.replace(",", "").replace("£", "").strip()
            if cleaned == "":
                return None
            return float(cleaned)
    except Exception:
        return None
    return None

