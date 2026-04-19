from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class CacheEntry:
    path: str
    etag: Optional[str]


class ExampleCache:
    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self._meta_path = os.path.join(self.cache_dir, "cache_index.json")
        self._meta = self._load_meta()

    def _load_meta(self) -> dict[str, dict[str, Any]]:
        if not os.path.exists(self._meta_path):
            return {}
        try:
            with open(self._meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_meta(self) -> None:
        with open(self._meta_path, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, ensure_ascii=True, indent=2, sort_keys=True)

    def get(self, blob_name: str, etag: Optional[str]) -> Optional[str]:
        entry = self._meta.get(blob_name)
        if not entry:
            return None
        if etag and entry.get("etag") and entry["etag"] != etag:
            return None
        path = entry.get("path")
        if not path or not os.path.exists(path):
            return None
        return path

    def put(self, blob_name: str, etag: Optional[str], content_bytes: bytes) -> str:
        safe_name = blob_name.replace("/", "__")
        path = os.path.join(self.cache_dir, safe_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content_bytes)
        self._meta[blob_name] = {"etag": etag, "path": path}
        self._save_meta()
        return path

