"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .report import to_json, to_markdown, to_text
from .similarity import analyze
from .sources import FetchError, fetch_crtsh, load_fixture
from .store import Store

DEMO_FIXTURE = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "crtsh_sample.json"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ct-lookalike",
        description="Hunt Certificate Transparency logs for domains that look like yours.",
    )
    p.add_argument("--brand", action="append", default=[],
                   help="brand token to protect, e.g. acmebank (repeatable)")
    p.add_argument("--alias", action="append", default=[],
                   help="additional brand spelling to match (repeatable)")
    p.add_argument("--fixture", help="read crt.sh-shaped JSON instead of the network")
    p.add_argument("--demo", action="store_true",
                   help="use the bundled sample feed (implies --brand acmebank)")
    p.add_argument("--db", default="ct-lookalike.sqlite3",
                   help="state database (default: %(default)s)")
    p.add_argument("--threshold", type=float, default=0.55,
                   help="minimum score to report (default: %(default)s)")
    p.add_argument("--format", choices=("md", "text", "json"), default="md")
    p.add_argument("--out", help="write report to a file instead of stdout")
    p.add_argument("--no-store", action="store_true",
                   help="report everything, do not suppress previously seen domains")
    p.add_argument("--fail-on-hit", action="store_true",
                   help="exit 1 when anything meets the threshold (for CI)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:  # Windows consoles default to cp1252
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):  # pragma: no cover
                pass

    brands = list(args.brand)
    if args.demo:
        args.fixture = str(DEMO_FIXTURE)
        if not brands:
            brands = ["acmebank.com"]
    if not brands:
        print("error: --brand is required (or use --demo)", file=sys.stderr)
        return 2

    if args.fixture:
        try:
            entries = load_fixture(args.fixture)
        except (OSError, ValueError) as exc:
            print(f"error: cannot read fixture: {exc}", file=sys.stderr)
            return 2
    else:
        entries = []
        for brand in brands:
            try:
                entries.extend(fetch_crtsh(brand))
            except FetchError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 3

    domains = sorted({e.domain for e in entries})
    hits = analyze(domains, brands[0], aliases=brands[1:], threshold=args.threshold)

    if not args.no_store:
        with Store(args.db) as store:
            fresh = [c for c in hits if store.record(c.domain, brands[0], c.score)]
        hits = fresh

    if args.format == "json":
        report = to_json(hits, brands[0])
    elif args.format == "text":
        report = to_text(hits, brands[0])
    else:
        report = to_markdown(hits, brands[0])

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"wrote {args.out} ({len(hits)} finding(s))", file=sys.stderr)
    else:
        sys.stdout.write(report)

    return 1 if (args.fail_on_hit and hits) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
