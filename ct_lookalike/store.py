"""SQLite-backed "already reported this" state."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    domain      TEXT NOT NULL,
    brand       TEXT NOT NULL,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    score       REAL NOT NULL,
    PRIMARY KEY (domain, brand)
);
CREATE INDEX IF NOT EXISTS idx_seen_brand ON seen(brand);
"""


@dataclass
class SeenRow:
    domain: str
    first_seen: str
    last_seen: str
    brand: str
    score: float


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def is_known(self, domain: str, brand: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM seen WHERE domain = ? AND brand = ?", (domain, brand)
        )
        return cur.fetchone() is not None

    def record(self, domain: str, brand: str, score: float) -> bool:
        """Insert or bump a domain. Returns True if it was new."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cur = self._conn.execute(
            "SELECT 1 FROM seen WHERE domain = ? AND brand = ?", (domain, brand)
        )
        if cur.fetchone():
            self._conn.execute(
                "UPDATE seen SET last_seen = ?, score = MAX(score, ?) "
                "WHERE domain = ? AND brand = ?",
                (now, score, domain, brand),
            )
            self._conn.commit()
            return False
        self._conn.execute(
            "INSERT INTO seen(domain, first_seen, last_seen, brand, score) "
            "VALUES (?, ?, ?, ?, ?)",
            (domain, now, now, brand, score),
        )
        self._conn.commit()
        return True

    def filter_new(self, domains: Iterable[str], brand: str,
                   score: float = 0.0) -> list[str]:
        """Return domains not yet stored, recording them as seen."""
        fresh = []
        for domain in domains:
            if self.record(domain, brand, score):
                fresh.append(domain)
        return fresh

    def rows(self, brand: str | None = None) -> list[SeenRow]:
        sql = "SELECT domain, first_seen, last_seen, brand, score FROM seen"
        args: tuple = ()
        if brand is not None:
            sql += " WHERE brand = ?"
            args = (brand,)
        sql += " ORDER BY score DESC, domain ASC"
        return [SeenRow(*row) for row in self._conn.execute(sql, args)]
