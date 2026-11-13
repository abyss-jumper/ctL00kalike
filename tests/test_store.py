import tempfile
import unittest
from pathlib import Path

from ct_lookalike.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_record_is_new(self):
        with Store(self.path) as store:
            self.assertTrue(store.record("evil.test", "brand", 0.9))

    def test_second_record_is_not_new(self):
        with Store(self.path) as store:
            store.record("evil.test", "brand", 0.9)
            self.assertFalse(store.record("evil.test", "brand", 0.95))

    def test_score_keeps_maximum(self):
        with Store(self.path) as store:
            store.record("evil.test", "brand", 0.9)
            store.record("evil.test", "brand", 0.4)
            self.assertEqual(store.rows("brand")[0].score, 0.9)

    def test_filter_new_only_returns_unseen(self):
        with Store(self.path) as store:
            store.record("seen.test", "brand", 0.8)
            fresh = store.filter_new(["seen.test", "new.test"], "brand")
            self.assertEqual(fresh, ["new.test"])

    def test_brands_are_namespaced(self):
        with Store(self.path) as store:
            store.record("shared.test", "brand-a", 0.8)
            self.assertTrue(store.record("shared.test", "brand-b", 0.8))

    def test_rows_sorted_by_score(self):
        with Store(self.path) as store:
            store.record("low.test", "b", 0.6)
            store.record("high.test", "b", 0.9)
            self.assertEqual([r.domain for r in store.rows("b")],
                             ["high.test", "low.test"])


if __name__ == "__main__":
    unittest.main()
