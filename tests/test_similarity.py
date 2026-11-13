import unittest

from ct_lookalike.similarity import (
    analyze,
    normalize,
    osa_distance,
    registrable,
    score_candidate,
    skeleton,
    split_domain,
)


class SkeletonTests(unittest.TestCase):
    def test_cyrillic_folds_to_ascii(self):
        self.assertEqual(skeleton("\u0430cmebank"), "acmebank")

    def test_rn_folds_to_m(self):
        self.assertEqual(skeleton("acrnebank"), "acmebank")

    def test_digits_fold(self):
        self.assertEqual(skeleton("paypa1"), "paypal")

    def test_plain_ascii_untouched(self):
        self.assertEqual(skeleton("example"), "example")


class DomainParsingTests(unittest.TestCase):
    def test_split_simple(self):
        self.assertEqual(split_domain("acmebank.co.uk"), ("acmebank", "co.uk"))

    def test_split_com(self):
        self.assertEqual(split_domain("mail.example.com"), ("example", "com"))

    def test_registrable_multi_label_suffix(self):
        self.assertEqual(registrable("a.b.example.co.uk"), "example.co.uk")

    def test_normalize_strips_wildcard_and_dot(self):
        self.assertEqual(normalize("*.Example.COM."), "example.com")

    def test_normalize_decodes_punycode(self):
        self.assertEqual(normalize("xn--bcher-kva.example"), "bücher.example")


class DistanceTests(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(osa_distance("abc", "abc"), 0)

    def test_substitution(self):
        self.assertEqual(osa_distance("acmebank", "acmebenk"), 1)

    def test_transposition_counts_once(self):
        self.assertEqual(osa_distance("acmebnak", "acmebank"), 1)

    def test_far_apart_is_capped(self):
        self.assertGreater(osa_distance("aaaa", "bbbbbbbb"), 4)


class ScoringTests(unittest.TestCase):
    def test_own_domain_scores_zero(self):
        self.assertEqual(score_candidate("acmebank.com", "acmebank.com").score, 0.0)
        self.assertEqual(score_candidate("www.acmebank.com", "acmebank.com").score, 0.0)

    def test_same_label_other_tld(self):
        cand = score_candidate("acmebank.co", "acmebank.com")
        self.assertGreaterEqual(cand.score, 0.85)
        self.assertEqual(cand.tier, "critical")

    def test_homoglyph_domain(self):
        cand = score_candidate("\u0430cmebank.com", "acmebank.com")
        self.assertGreaterEqual(cand.score, 0.8)
        self.assertIn("confusable", " ".join(cand.reasons))

    def test_keyboard_typo(self):
        cand = score_candidate("acnebank.com", "acmebank.com")
        self.assertGreaterEqual(cand.score, 0.8)

    def test_hyphenated_lure(self):
        cand = score_candidate("acmebank-secure.com", "acmebank.com")
        self.assertEqual(cand.score, 1.0)

    def test_embedded_brand(self):
        self.assertGreaterEqual(
            score_candidate("acmebankkyc.com", "acmebank.com").score, 0.55
        )

    def test_risky_tld_pushes_score(self):
        self.assertGreater(
            score_candidate("acmebank.tk", "acmebank.com").score,
            score_candidate("acmebank.co", "acmebank.com").score,
        )

    def test_unrelated_domain_ignored(self):
        self.assertLess(score_candidate("example.com", "acmebank.com").score, 0.3)

    def test_semantically_similar_but_distinct(self):
        self.assertLess(score_candidate("acmelabs.io", "acmebank.com").score, 0.55)

    def test_alias_matches(self):
        cand = score_candidate("acme-bank.co", "acmebank.com", aliases=["acme-bank"])
        self.assertGreaterEqual(cand.score, 0.8)

    def test_analyze_filters_and_sorts(self):
        hits = analyze(
            ["acmebank.co", "acmebank.tk", "example.com", "acmebank.com"],
            "acmebank.com",
            threshold=0.55,
        )
        self.assertEqual([h.domain for h in hits][:2], ["acmebank.tk", "acmebank.co"])
        self.assertNotIn("example.com", [h.domain for h in hits])
        self.assertNotIn("acmebank.com", [h.domain for h in hits])


if __name__ == "__main__":
    unittest.main()
