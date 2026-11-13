#!/usr/bin/env python3
"""Measure precision / recall of the similarity scorer on a labelled corpus.

This is intentionally tiny and boring: a labelled CSV in, a metrics table out.
Append rows to ``corpus/lookalike_labels.csv`` when you find a miss.

Usage:
    python tools/benchmark.py [--threshold 0.55] [--min-recall 0.85]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ct_lookalike.similarity import score_candidate  # noqa: E402

CORPUS = ROOT / "corpus" / "lookalike_labels.csv"


def load(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def evaluate(rows: list[dict], threshold: float) -> dict:
    tp = fp = tn = fn = 0
    misses, false_alarms = [], []
    for row in rows:
        score = score_candidate(row["domain"], row["brand"]).score
        predicted = score >= threshold
        actual = row["label"] == "1"
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
            false_alarms.append((row["domain"], score))
        elif actual:
            fn += 1
            misses.append((row["domain"], score))
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    accuracy = (tp + tn) / len(rows) if rows else 0.0
    return {
        "threshold": threshold, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1, "fpr": fpr,
        "accuracy": accuracy, "misses": misses, "false_alarms": false_alarms,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--sweep", action="store_true", help="print a threshold sweep")
    ap.add_argument("--min-recall", type=float, default=None)
    ap.add_argument("--max-fpr", type=float, default=None)
    args = ap.parse_args(argv)

    rows = load(args.corpus)
    if args.sweep:
        print(f"{'thr':>5} {'prec':>6} {'rec':>6} {'f1':>6} {'fpr':>6}")
        for step in range(30, 91, 5):
            m = evaluate(rows, step / 100)
            print(f"{m['threshold']:>5.2f} {m['precision']:>6.2f} "
                  f"{m['recall']:>6.2f} {m['f1']:>6.2f} {m['fpr']:>6.2f}")

    m = evaluate(rows, args.threshold)
    print(f"\ncorpus: {args.corpus} ({len(rows)} rows)")
    print(f"threshold {m['threshold']:.2f}  TP={m['tp']} FP={m['fp']} "
          f"TN={m['tn']} FN={m['fn']}")
    print(f"precision {m['precision']:.2f}  recall {m['recall']:.2f}  "
          f"f1 {m['f1']:.2f}  fpr {m['fpr']:.2f}  accuracy {m['accuracy']:.2f}")

    if m["misses"]:
        print("\nmisses:")
        for domain, score in m["misses"]:
            print(f"  {score:.2f}  {domain}")
    if m["false_alarms"]:
        print("\nfalse alarms:")
        for domain, score in m["false_alarms"]:
            print(f"  {score:.2f}  {domain}")

    failed = False
    if args.min_recall is not None and m["recall"] < args.min_recall:
        print(f"\nFAIL: recall {m['recall']:.2f} < {args.min_recall:.2f}")
        failed = True
    if args.max_fpr is not None and m["fpr"] > args.max_fpr:
        print(f"\nFAIL: fpr {m['fpr']:.2f} > {args.max_fpr:.2f}")
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
