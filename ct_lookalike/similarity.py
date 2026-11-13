"""Domain similarity scoring.

The goal is *not* to be a general-purpose fuzzy matcher. It is to answer one
question: "would a tired person plausibly type this domain when they meant
`acmebank.com`?"  Everything here is deterministic and offline, so the scores
can be regression-tested.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Sequence

# ---------------------------------------------------------------------------
# Character skeleton
# ---------------------------------------------------------------------------
# A deliberately small, hand-audited confusable map. Each entry is a character
# that renders (near-)identically to the ASCII target in common UI fonts.
CONFUSABLES = {
    # Cyrillic
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p", "\u0441": "c",
    "\u0445": "x", "\u0443": "y", "\u0456": "i", "\u0458": "j", "\u0455": "s",
    "\u0501": "d", "\u04bb": "h", "\u043a": "k", "\u043c": "m", "\u0442": "t",
    "\u0432": "b", "\u043d": "h", "\u0261": "g",
    # Greek
    "\u03b1": "a", "\u03b5": "e", "\u03bf": "o", "\u03c1": "p", "\u03bd": "v",
    "\u03b9": "i", "\u03ba": "k", "\u03c5": "u", "\u03c7": "x", "\u03b3": "y",
    # Latin extensions / punctuation lookalikes
    "\u0131": "i", "\u0237": "j", "\u00df": "ss", "\u00e6": "ae", "\u0153": "oe",
    "\u00f8": "o", "\u0111": "d", "\u0142": "l", "\u01c0": "l",
    # Digit / symbol substitutions
    "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b",
    "$": "s", "@": "a", "!": "i", "|": "l",
}

# Terms attackers append to a brand. Presence adds a small amount of suspicion.
LURE_WORDS = {
    "login", "signin", "sign-in", "secure", "security", "verify", "verification",
    "account", "accounts", "support", "help", "update", "wallet", "app", "my",
    "online", "portal", "pay", "payment", "billing", "auth", "service", "team",
    "official", "recovery", "unlock", "confirm", "id", "web", "site",
}

# TLDs with a poor abuse reputation (Spamhaus / Interisle style lists, curated).
RISKY_TLDS = {
    "zip", "mov", "tk", "ml", "ga", "cf", "gq", "top", "xyz", "click", "link",
    "work", "loan", "review", "country", "stream", "download", "racing", "win",
    "bid", "party", "science", "gdn", "icu", "cyou", "buzz", "rest", "cam",
}

# Very small public-suffix subset. Good enough for scoring, not for a browser.
MULTI_LABEL_SUFFIXES = {
    "co.uk", "org.uk", "gov.uk", "ac.uk", "me.uk", "net.uk", "sch.uk",
    "com.au", "net.au", "org.au", "edu.au", "gov.au", "id.au",
    "co.jp", "or.jp", "ne.jp", "ac.jp", "go.jp",
    "co.nz", "net.nz", "org.nz", "govt.nz",
    "co.za", "org.za", "net.za", "gov.za",
    "com.br", "net.br", "org.br", "gov.br",
    "co.in", "net.in", "org.in", "gov.in",
    "com.cn", "net.cn", "org.cn", "gov.cn",
    "com.mx", "com.tr", "com.sg", "com.hk", "com.tw", "co.kr", "or.kr",
    "co.il", "org.il", "com.ar", "com.pl", "com.ua", "co.id", "com.my",
    "com.ph", "com.vn", "com.pk", "com.ng", "com.eg", "com.sa", "com.es",
}


def normalize(host: str) -> str:
    """Lowercase, strip a trailing dot, and decode punycode when possible."""
    host = host.strip().lower().rstrip(".")
    if host.startswith("*."):
        host = host[2:]
    if "xn--" in host:
        try:
            host = host.encode("ascii").decode("idna").lower()
        except (UnicodeError, ValueError):
            pass
    return host


def skeleton(text: str) -> str:
    """Fold a string down to its visual skeleton."""
    text = unicodedata.normalize("NFKD", text).lower()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    folded = "".join(CONFUSABLES.get(ch, ch) for ch in text)
    # Multi-character folds that are common in typosquats.
    folded = folded.replace("rn", "m").replace("vv", "w").replace("cl", "d")
    return folded


def split_domain(host: str) -> tuple[str, str]:
    """Return (label, public suffix) for a normalized host."""
    labels = host.split(".")
    if len(labels) < 2:
        return host, ""
    for size in (3, 2):
        if len(labels) > size:
            suffix = ".".join(labels[-size:])
            if suffix in MULTI_LABEL_SUFFIXES:
                return labels[-size - 1], suffix
    return labels[-2], ".".join(labels[-1:])


def registrable(host: str) -> str:
    """Approximate eTLD+1."""
    host = normalize(host)
    label, suffix = split_domain(host)
    return f"{label}.{suffix}" if suffix else label


# ---------------------------------------------------------------------------
# Distances
# ---------------------------------------------------------------------------
KEY_ROWS = ("1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm")


def _keyboard_neighbours() -> dict[str, set[str]]:
    coords = {}
    for y, row in enumerate(KEY_ROWS):
        for x, ch in enumerate(row):
            coords[ch] = (x, y)
    out: dict[str, set[str]] = {ch: set() for ch in coords}
    for ch, (x, y) in coords.items():
        for other, (ox, oy) in coords.items():
            if (abs(x - ox) <= 1 and abs(y - oy) <= 1) and (x, y) != (ox, oy):
                out[ch].add(other)
    return out


KEY_NEIGHBOURS = _keyboard_neighbours()


def osa_distance(a: str, b: str, cap: int = 4) -> int:
    """Optimal string alignment distance (Levenshtein + transpositions)."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev2: Sequence[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > cap:
            return cap + 1
        prev2, prev = prev, cur
    return min(prev[len(b)], cap + 1)


def keyboard_substitutions(candidate: str, brand: str) -> int:
    """Count positions where one character is a QWERTY neighbour of the other."""
    if len(candidate) != len(brand):
        return 0
    return sum(
        1 for c, b in zip(candidate, brand)
        if c != b and c in KEY_NEIGHBOURS and b in KEY_NEIGHBOURS[c]
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    domain: str
    brand: str
    score: float
    reasons: list[str] = field(default_factory=list)
    features: dict[str, float] = field(default_factory=dict)

    @property
    def tier(self) -> str:
        if self.score >= 0.85:
            return "critical"
        if self.score >= 0.7:
            return "high"
        if self.score >= 0.55:
            return "medium"
        return "low"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_candidate(raw_domain: str, brand: str,
                    aliases: Iterable[str] = ()) -> Candidate:
    """Score one host against a brand and any known aliases."""
    display = raw_domain.strip().lower().rstrip(".")
    if display.startswith("*."):
        display = display[2:]
    domain = normalize(raw_domain)
    brand = normalize(brand)
    best = Candidate(domain=domain, brand=brand, score=0.0)
    for token in [brand, *(normalize(a) for a in aliases)]:
        cand = _score_one(domain, token)
        if cand.score > best.score:
            best = cand
    # Report the original spelling (usually punycode) so it can be blocked.
    best.domain = display or domain
    return best


def _score_one(domain: str, brand: str) -> Candidate:
    label, suffix = split_domain(domain)
    brand_label, brand_suffix = split_domain(brand)
    brand_label = brand_label or brand

    feats: dict[str, float] = {}
    reasons: list[str] = []
    score = 0.0

    def add(name: str, value: float, reason: str | None = None) -> None:
        nonlocal score
        feats[name] = value
        score += value
        if reason:
            reasons.append(reason)

    sk_label = skeleton(label)
    sk_brand = skeleton(brand_label)

    if label == brand_label and suffix == brand_suffix:
        # The brand's own registrable domain (including subdomains of it).
        return Candidate(domain=domain, brand=brand, score=0.0,
                         reasons=["brand's own domain"])

    if label == brand_label:
        score = 0.88
        feats["same_label"] = score
        reasons.append(
            "identical label, different TLD "
            f"(.{suffix or 'none'} vs .{brand_suffix or 'none'})"
        )
    elif sk_label == sk_brand:
        add("skeleton_match", 0.82, f"identical after confusable folding ({sk_label})")

    if score == 0.0:
        dist = osa_distance(label, brand_label)
        if dist == 1:
            add("edit_distance_1", 0.64, "one edit away from the brand")
        elif dist == 2:
            add("edit_distance_2", 0.4, "two edits away from the brand")

        subs = keyboard_substitutions(label, brand_label)
        if subs and dist <= 2:
            add("keyboard_adjacent", 0.22, f"{subs} keyboard-adjacent key(s)")

        if brand_label and brand_label in label and label != brand_label:
            extra = len(label) - len(brand_label)
            if 0 < extra <= 6:
                add("embedded_brand", 0.6,
                    f"brand embedded with {extra} extra character(s)")
            else:
                add("embedded_brand", 0.62 * (len(brand_label) / len(label)),
                    "brand partially embedded")

        tokens = [t for t in label.replace("_", "-").split("-") if t]
        if len(tokens) > 1 and brand_label in tokens:
            add("hyphen_inserted_brand", 0.58,
                "brand split by a hyphen")

        if tokens and (tokens[0] in LURE_WORDS or tokens[-1] in LURE_WORDS) \
                and sk_brand in skeleton(label):
            add("lure_word", 0.12, "contains a credential-themed lure word")

        if domain.startswith("xn--") or ".xn--" in domain:
            add("punycode", 0.1, "internationalized (punycode) domain")

    if suffix in RISKY_TLDS:
        add("risky_tld", 0.09, f"high-abuse TLD .{suffix}")

    # Long random labels are usually squatters, not impersonators.
    if len(label) > max(12, len(brand_label) * 2.5):
        score *= 0.75
        reasons.append("label is long; score damped")

    cand = Candidate(domain=domain, brand=brand, score=round(_clamp(score), 3),
                     reasons=reasons, features=feats)
    return cand


def analyze(domains: Iterable[str], brand: str,
            aliases: Iterable[str] = (), threshold: float = 0.55
            ) -> list[Candidate]:
    """Score many hosts, returning only those at/above ``threshold``."""
    hits = []
    for domain in domains:
        cand = score_candidate(domain, brand, aliases)
        if cand.score >= threshold:
            hits.append(cand)
    return sorted(hits, key=lambda c: (-c.score, c.domain))
