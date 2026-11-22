# ct-lookalike

Hunt Certificate Transparency logs for domains that *look* like yours ie typosquats,
homoglyphs, hyphenated lures etc. before the phishing site gets its certificate.

pure python, deterministic scoring, sqLite state

```text
$ ct-lookalike --demo --format text
Lookalike domains for acmebank.com (2026-11-12 08:00 UTC)
  1.00  critical  acmebank-login.top       brand embedded with 6 extra character(s); brand split by a hyphen; contains a credential-themed lure word; high-abuse TLD .top
  1.00  critical  acmebank-secure.com      brand partially embedded; brand split by a hyphen; contains a credential-themed lure word
  1.00  critical  www.acmebank-secure.com  brand partially embedded; brand split by a hyphen; contains a credential-themed lure word
  0.88  critical  acmebank.co              identical label, different TLD (.co vs .com)
  0.86  critical  acnebank.com             one edit away from the brand; 1 keyboard-adjacent key(s)
  0.82  high      acrnebank.com            identical after confusable folding (acmebank)
  0.82  high      xn--cmebank-1fg.com      identical after confusable folding (acmebank)
  0.60  medium    acmebankkyc.com          brand embedded with 3 extra character(s)
  0.60  medium    notacmebank.com          brand embedded with 3 extra character(s)
```

## Install

```bash
git clone https://github.com/abyss-jumper/ctL00kalike
cd ct-lookalike
python -m pip install -e .
ct-lookalike --demo               # offline, uses the bundled sample feed
```

Python 3.9+. No third-party packages.

## Usage

```bash
# live crt.sh query, markdown digest to stdout
ct-lookalike --brand example.com

# suppress anything already seen in earlier runs
ct-lookalike --brand example.com --db state.sqlite3 --out digest.md

# CI gate: fail the job if a new lookalike appears
ct-lookalike --brand example.com --fail-on-hit --format text

# extra spellings / acquired brands
ct-lookalike --brand example.com --alias examplebank.com

# machine-readable
ct-lookalike --brand example.com --format json
```

On Windows the default database is `ct-lookalike.sqlite3` in the working
directory. Add it to `.gitignore` (already done here).

### Scheduling

A daily GitHub Action is enough:

```yaml
name: lookalike-watch
on:
  schedule: [{ cron: "17 6 * * *" }]
  workflow_dispatch:
jobs:
  watch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e .
      - run: ct-lookalike --brand example.com --db state.sqlite3 --out digest.md
      - run: cat digest.md >> "$GITHUB_STEP_SUMMARY"
      # commit state.sqlite3 back, or upload it as an artifact
```

## How the score works

Each candidate host is reduced to a *skeleton*: NFKD-normalise, strip combining
marks, fold a hand-audited confusable table (Cyrillic/Greek lookalikes, `0→o`,
`1→l`, `rn→m`, …), then compare against the brand.

Additive features, clamped to `[0, 1]`:

| feature | weight | example |
|---|---|---|
| identical label, different TLD | 0.88 | `brand.co` vs `brand.com` |
| identical after confusable folding | 0.82 | `аcmebank.com`, `acrnebank.com` |
| embedded brand + ≤6 chars | 0.60 | `brandkyc.com` |
| brand split by hyphen | 0.58 | `brand-secure.com` |
| one edit away | 0.64 | `acmebenk.com` |
| keyboard-adjacent substitution | +0.22 | `acnebank.com` |
| credential lure word | +0.12 | `...-login`, `...-verify` |
| high-abuse TLD | +0.09 | `.tk`, `.top`, `.zip` |
| punycode | +0.10 | `xn--...` |

Tiers: `critical ≥ 0.85`, `high ≥ 0.70`, `medium ≥ 0.55`.

Run the labelled corpus in CI:

```bash
python tools/benchmark.py --sweep
```

On the bundled 40-row corpus at threshold 0.55: **precision 1.00, recall 1.00,
FPR 0.00**. That corpus is small and self-selected — treat it as a regression
guard, not a claim about the internet.

## Layout

```
ct_lookalike/
  similarity.py   skeleton folding, distances, scoring
  sources.py      crt.sh client + fixture loader
  store.py        SQLite seen-set (per brand)
  report.py       markdown / text / json
  cli.py          argument parsing and orchestration
corpus/           labelled lookalike corpus
data/fixtures/    offline crt.sh sample
tools/benchmark.py
tests/            39 unittest cases, no network
```
