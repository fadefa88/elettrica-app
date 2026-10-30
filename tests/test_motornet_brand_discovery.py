"""Regression tests for Motornet brand discovery and source-availability safety."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sync_motornet_catalog as sync  # noqa: E402


class MotornetBrandDiscoveryTests(unittest.TestCase):
    def test_search_filter_values_are_not_brands(self) -> None:
        prefix = f"{sync.base.BASE}/auto/scheda-modello/"
        candidates = [
            prefix + "5000", prefix + "IB", prefix + "SUV",
            prefix + "AUD", prefix + "BMW", prefix + "AUD",
            prefix + "COR",
        ]
        self.assertEqual(sync.filter_valid_brand_urls(candidates), [
            prefix + "AUD", prefix + "BMW",
        ])

    def test_empty_valid_discovery_falls_back_to_known_brands(self) -> None:
        page = SimpleNamespace(goto=MagicMock(), wait_for_timeout=MagicMock())
        args = SimpleNamespace(brand_codes="", timeout=10000)
        fake_values = [
            f"{sync.base.BASE}/auto/scheda-modello/5000",
            f"{sync.base.BASE}/auto/scheda-modello/IB",
        ]
        with (
            patch.object(sync.base, "can_fetch", return_value=True),
            patch.object(sync.base, "extract_links", return_value=fake_values),
            patch.object(sync.base, "open_possible_dropdowns") as open_menus,
        ):
            brands, requests = sync.build_brand_urls(page, args, object(), [])
        self.assertEqual(requests, 1)
        open_menus.assert_called_once_with(page)
        self.assertIn(f"{sync.base.BASE}/auto/scheda-modello/AUD", brands)
        self.assertNotIn(fake_values[0], brands)
        self.assertNotIn(fake_values[1], brands)

    def test_no_details_for_two_major_brands_stops_without_catalog_write(self) -> None:
        page = SimpleNamespace(goto=MagicMock(), wait_for_timeout=MagicMock())
        args = SimpleNamespace(brand_codes="", timeout=10000, delay=0)
        brands = [
            f"{sync.base.BASE}/auto/scheda-modello/AUD",
            f"{sync.base.BASE}/auto/scheda-modello/BMW",
        ]
        with (
            patch.object(sync.base, "can_fetch", return_value=True),
            patch.object(sync.base, "discover_links_after_clicking_menus", return_value=[]),
            patch.object(sync.time, "sleep"),
        ):
            with self.assertRaisesRegex(SystemExit, "Safety stop: no vehicle details"):
                sync.discover_active_detail_urls(page, brands, args, object(), [])
        self.assertEqual(page.goto.call_count, 2)


if __name__ == "__main__":
    unittest.main()
