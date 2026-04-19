from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, Iterable, Optional

from experiments.types import GenerationRecord, RunDefinition


class SqliteExperimentStore:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                  run_id TEXT PRIMARY KEY,
                  created_at REAL NOT NULL,
                  run_name TEXT NOT NULL,
                  run_def_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS generations (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  run_id TEXT NOT NULL,
                  example_id TEXT NOT NULL,
                  model_id TEXT NOT NULL,
                  technique TEXT NOT NULL,
                  context_mode TEXT NOT NULL,
                  prompt_hash TEXT NOT NULL,
                  context_hash TEXT NOT NULL,
                  latency_s REAL NOT NULL,
                  usage_json TEXT NOT NULL,
                  score_json TEXT NOT NULL,
                  prompt_text TEXT NOT NULL,
                  context_text TEXT NOT NULL,
                  output_text TEXT NOT NULL,
                  created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_generations_run_id ON generations(run_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_generations_example ON generations(example_id)"
            )

    def create_run(self, run_id: str, run_def: RunDefinition) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs(run_id, created_at, run_name, run_def_json) VALUES (?, ?, ?, ?)",
                (
                    run_id,
                    time.time(),
                    run_def.run_name,
                    json.dumps(run_def, default=lambda o: o.__dict__, ensure_ascii=True),
                ),
            )

    def add_generation(self, rec: GenerationRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO generations(
                  run_id, example_id, model_id, technique, context_mode,
                  prompt_hash, context_hash, latency_s,
                  usage_json, score_json, prompt_text, context_text, output_text, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.run_id,
                    rec.example_id,
                    rec.model_id,
                    rec.technique,
                    rec.context_mode,
                    rec.prompt_hash,
                    rec.context_hash,
                    rec.latency_s,
                    json.dumps(rec.usage_json, ensure_ascii=True),
                    json.dumps(rec.score_json, ensure_ascii=True),
                    rec.prompt_text,
                    rec.context_text,
                    rec.output_text,
                    time.time(),
                ),
            )

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT run_id, created_at, run_name FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT run_id, created_at, run_name, run_def_json FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_generations(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                  example_id, model_id, technique, context_mode,
                  latency_s, prompt_hash, context_hash, usage_json, score_json, output_text
                FROM generations
                WHERE run_id=?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["usage_json"] = json.loads(d["usage_json"])
            d["score_json"] = json.loads(d["score_json"])
            out.append(d)
        return out

    def export_generations_csv_rows(self, run_id: str) -> Iterable[list[str]]:
        gens = self.list_generations(run_id)
        yield [
            "run_id",
            "example_id",
            "model_id",
            "technique",
            "context_mode",
            "latency_s",
            "prompt_hash",
            "context_hash",
            "usage_json",
            "score_json",
            "output_text",
        ]
        for g in gens:
            yield [
                run_id,
                str(g["example_id"]),
                str(g["model_id"]),
                str(g["technique"]),
                str(g["context_mode"]),
                str(g["latency_s"]),
                str(g["prompt_hash"]),
                str(g["context_hash"]),
                json.dumps(g["usage_json"], ensure_ascii=True),
                json.dumps(g["score_json"], ensure_ascii=True),
                str(g["output_text"]),
            ]

