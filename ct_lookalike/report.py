"""Render findings as Markdown, plain text, or JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from .similarity import Candidate


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def to_json(candidates: Iterable[Candidate], brand: str) -> str:
    payload = {
        "brand": brand,
        "generated_at": _now(),
        "count": len(list(candidates)),
        "findings": [c.__dict__ for c in candidates],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def to_markdown(candidates: list[Candidate], brand: str, max_rows: int = 100) -> str:
    lines = [
        f"# Lookalike domains for `{brand}`",
        "",
        f"_{_now()} — {len(candidates)} candidate(s) at or above threshold._",
        "",
    ]
    if not candidates:
        lines.append("No new lookalike domains. 🎉")
        return "\n".join(lines) + "\n"

    lines += [
        "| score | tier | domain | why |",
        "|------:|:-----|:-------|:----|",
    ]
    for cand in candidates[:max_rows]:
        why = "; ".join(cand.reasons) or "—"
        why = why.replace("|", "\\|")
        lines.append(
            f"| {cand.score:.2f} | {cand.tier} | `{cand.domain}` | {why} |"
        )
    if len(candidates) > max_rows:
        lines.append(f"\n_… {len(candidates) - max_rows} more truncated._")
    lines += [
        "",
        "> Scores are heuristics, not proof. Verify before contacting anyone.",
    ]
    return "\n".join(lines) + "\n"


def to_text(candidates: list[Candidate], brand: str) -> str:
    lines = [f"Lookalike domains for {brand} ({_now()})"]
    if not candidates:
        return lines[0] + "\n\nNo candidates.\n"
    width = max(len(c.domain) for c in candidates)
    for cand in candidates:
        lines.append(
            f"  {cand.score:.2f}  {cand.tier:<8}  {cand.domain:<{width}}  "
            f"{'; '.join(cand.reasons)}"
        )
    return "\n".join(lines) + "\n"
