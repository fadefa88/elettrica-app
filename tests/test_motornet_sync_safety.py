"""Regression coverage for safe Motornet daily synchronization."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import import_motornet_resume as resume
import sync_motornet_catalog as sync


BASE = "https://www.motornet.it/auto/scheda-modello"


def detail(code: str, model: int = 1) -> str:
    return f"{BASE}/modello/{model}/allestimento/{code}"


class MotornetSyncSafetyTests(unittest.TestCase):
    def test_large_deletion_is_quarantined(self):
        existing = {str(i) for i in range(5656)}
        active = {str(i) for i in range(4321)}
        approved, candidates, reason = sync.plan_catalog_removals(
            existing, active, 0.10, False, []
        )
        self.assertEqual(approved, set())
        self.assertEqual(len(candidates), 1335)
        self.assertIn("exceed", reason)

    def test_manual_override_allows_large_deletion(self):
        approved, candidates, reason = sync.plan_catalog_removals(
            {"a", "b", "c"}, {"a"}, 0.10, True, []
        )
        self.assertEqual(approved, {"b", "c"})
        self.assertEqual(candidates, approved)
        self.assertEqual(reason, "")

    def test_scan_error_prevents_deletion_even_when_overridden(self):
        approved, candidates, reason = sync.plan_catalog_removals(
            {"a", "b"}, {"a"}, 0.10, True,
            [{"url": "example", "error": "model_expand: timeout"}],
        )
        self.assertEqual(approved, set())
        self.assertEqual(candidates, {"b"})
        self.assertIn("scan errors", reason)

    def test_disabled_deletion_preserves_unlisted_existing_records(self):
        old = {"id": "old", "brand": "Audi", "source_url": detail("AUD0001")}
        current = {"id": "current", "brand": "BMW", "source_url": detail("BMW0002")}
        cars = {old["source_url"]: old, current["source_url"]: current}
        self.assertEqual(
            sync.order_catalog_cars([current["source_url"]], cars, True),
            [old, current],
        )
        self.assertEqual(
            sync.order_catalog_cars([current["source_url"]], cars, False),
            [current],
        )

    def test_known_brand_codes_are_not_discarded_as_filters(self):
        valid = [
            f"{BASE}/DRM", f"{BASE}/DSA", f"{BASE}/MGG",
            f"{BASE}/KGM", f"{BASE}/EMC",
        ]
        invalid = [f"{BASE}/IB", f"{BASE}/SUV"]
        self.assertEqual(sync.filter_valid_brand_urls(valid + invalid), valid)

    def test_smart_allestimento_brand_alias(self):
        self.assertEqual(resume.brand_code_from_detail_url(detail("MCC1540")), "SMA")
        self.assertEqual(resume.brand_code_from_detail_url(detail("DRM0694")), "DRM")
        self.assertEqual(resume.brand_code_from_detail_url(detail("DSA0724")), "DSA")

    def test_corvette_remains_explicitly_ignored(self):
        self.assertTrue(sync.is_ignored_detail_url(detail("COR0559")))


if __name__ == "__main__":
    unittest.main()
