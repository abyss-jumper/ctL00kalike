"""Certificate Transparency feeds.

crt.sh is used rather than CertStream because it is queryable without a
long-lived websocket, which keeps this tool usable from a cron job or a
GitHub Action. Both paths are wrapped so they can be swapped in tests.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CRTSH_URL = "https://crt.sh/"
USER_AGENT = "ct-lookalike/0.1 (+https://github.com/)"


@dataclass
class CertEntry:
    domain: str
    issuer: str = ""
    not_before: str = ""
    entry_id: int | None = None


class FetchError(RuntimeError):
    pass


def _http_get(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def fetch_crtsh(brand: str, timeout: float = 30.0,
                getter=_http_get) -> list[CertEntry]:
    """Return every certificate entry whose name covers ``brand``.

    Two queries are issued: the apex and ``%.apex``. crt.sh treats them as
    different searches, and the first one is what catches the bare domain.
    """
    merged: dict[str, CertEntry] = {}
    last_error: Exception | None = None
    for pattern in (brand, f"%.{brand}"):
        query = urllib.parse.urlencode({"q": pattern, "output": "json"})
        url = f"{CRTSH_URL}?{query}"
        try:
            raw = getter(url, timeout=timeout)
            payload = json.loads(raw.decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001 - one of two queries may fail
            last_error = exc
            continue
        if not isinstance(payload, list):
            last_error = ValueError("unexpected crt.sh payload shape")
            continue
        for entry in entries_from_crtsh(payload):
            merged.setdefault(entry.domain, entry)
    if not merged and last_error is not None:
        raise FetchError(f"crt.sh request failed: {last_error}") from last_error
    return list(merged.values())


def entries_from_crtsh(payload: Iterable[dict]) -> list[CertEntry]:
    """Normalise raw crt.sh rows into unique CertEntry objects."""
    seen: set[str] = set()
    out: list[CertEntry] = []
    for row in payload:
        names = str(row.get("name_value", "")).splitlines()
        common = str(row.get("common_name", "") or "")
        if common:
            names.append(common)
        for name in names:
            name = name.strip().lower().lstrip("*.").rstrip(".")
            if not name or "." not in name or name in seen:
                continue
            seen.add(name)
            out.append(
                CertEntry(
                    domain=name,
                    issuer=str(row.get("issuer_name", "") or ""),
                    not_before=str(row.get("not_before", "") or ""),
                    entry_id=row.get("id"),
                )
            )
    return out


def load_fixture(path: str | Path) -> list[CertEntry]:
    """Load a crt.sh-shaped JSON file for offline runs and tests."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "entries" in data:
        data = data["entries"]
    return entries_from_crtsh(data)
