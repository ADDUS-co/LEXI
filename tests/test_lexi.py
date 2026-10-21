"""Run from the project root: python -m unittest discover -s tests -v."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path
import unittest
from unittest.mock import patch

from app import create_app
from lexi.catalog import load_catalog, validate_catalog
from lexi.selection import EPOCH, build_deck, select_word
from auth_support import signed_in_client

ROOT = Path(__file__).resolve().parents[1]


class VocabularyTests(unittest.TestCase):
    def setUp(self):
        self.collections, self.words, self.site = load_catalog(ROOT)

    def test_real_catalog_is_valid_and_complete(self):
        validate_catalog(self.collections, self.words)
        self.assertTrue(all(len(word["fullDefinition"]) >= len(word["shortDefinition"]) for word in self.words))
        self.assertEqual(len({word["id"] for word in self.words}), len(self.words))

    def test_duplicate_word_and_collection_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate word"):
            validate_catalog(self.collections, self.words + [self.words[0]])
        with self.assertRaisesRegex(ValueError, "Duplicate collection"):
            validate_catalog(self.collections + [self.collections[0]], self.words)

    def test_invalid_references_and_empty_collections_are_rejected(self):
        words = deepcopy(self.words)
        words[0]["collectionId"] = "missing"
        with self.assertRaisesRegex(ValueError, "Unknown collection"):
            validate_catalog(self.collections, words)
        with self.assertRaisesRegex(ValueError, "no vocabulary"):
            validate_catalog(self.collections, [word for word in self.words if word["collectionId"] != self.collections[0]["id"]])

    def test_missing_definitions_examples_and_invalid_objects_are_rejected(self):
        for field in ("shortDefinition", "fullDefinition", "simpleExplanation", "examples"):
            with self.subTest(field=field):
                words = deepcopy(self.words)
                words[0].pop(field)
                with self.assertRaises(ValueError):
                    validate_catalog(self.collections, words)
        with self.assertRaises(ValueError):
            validate_catalog(["not an object"], self.words)

    def test_optional_content_may_be_omitted(self):
        words = deepcopy(self.words)
        for word in words:
            for field in ("synonyms", "relatedWords", "source", "usageNote", "difficulty"):
                word.pop(field, None)
        validate_catalog(self.collections, words)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.collections, self.words, _ = load_catalog(ROOT)
        self.ids = [collection["id"] for collection in self.collections]

    def test_all_interest_subsets_complete_a_cycle_without_repetition(self):
        for size in range(1, len(self.ids) + 1):
            for selected in combinations(self.ids, size):
                deck = build_deck(self.collections, self.words, selected)
                result = [select_word(self.collections, self.words, selected, EPOCH + timedelta(days=i))["id"] for i in range(len(deck))]
                self.assertEqual(len(result), len(set(result)), selected)
                self.assertEqual(set(result), {word["id"] for word in self.words if word["collectionId"] in selected})
                self.assertEqual(select_word(self.collections, self.words, selected, EPOCH), select_word(self.collections, self.words, selected, EPOCH + timedelta(days=len(deck))))

    def test_selection_click_order_duplicates_and_refresh_do_not_change_result(self):
        selected = self.ids[:2]
        a = select_word(self.collections, self.words, selected, "2026-10-18")
        b = select_word(self.collections, self.words, list(reversed(selected)) + selected, "2026-10-18")
        self.assertEqual(a, b)

    def test_uneven_collections_are_interleaved_without_early_repetition(self):
        collections = [{"id": "a"}, {"id": "b"}]
        words = [{"id": "a1", "collectionId": "a"}, {"id": "a2", "collectionId": "a"}, {"id": "a3", "collectionId": "a"}, {"id": "b1", "collectionId": "b"}]
        self.assertEqual([word["id"] for word in build_deck(collections, words, ["b", "a"])], ["a1", "b1", "a2", "a3"])

    def test_before_epoch_and_leap_day_use_calendar_day_arithmetic(self):
        deck = build_deck(self.collections, self.words, self.ids)
        self.assertEqual(select_word(self.collections, self.words, self.ids, EPOCH - timedelta(days=1)), deck[-1])
        for day in (date(2024, 2, 29), date(2028, 2, 29)):
            word = select_word(self.collections, self.words, self.ids, day)
            self.assertEqual(word, deck[(day - EPOCH).days % len(deck)])

    def test_invalid_interests_and_empty_buckets_are_rejected(self):
        for selected in ([], ["missing"], [self.ids[0], "missing"]):
            with self.assertRaises(ValueError):
                build_deck(self.collections, self.words, selected)
        with self.assertRaises(ValueError):
            build_deck(self.collections, [], self.ids)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = signed_in_client(self.app)

    def test_home_catalog_and_daily_are_functional(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"main-content", home.data)
        catalog = self.client.get("/api/catalog").get_json()
        daily = self.client.get("/api/daily?collections=law,technology").get_json()
        expected = select_word(catalog["collections"], catalog["words"], ["law", "technology"], daily["date"])
        self.assertEqual(daily["word"], expected)
        self.assertEqual(daily["timezone"], "Asia/Bishkek")
        self.assertEqual(self.client.get("/health").get_json(), {"status": "ok"})

    def test_invalid_query_returns_400(self):
        for query in ("", "unknown", "law,unknown"):
            response = self.client.get("/api/daily", query_string={"collections": query})
            self.assertEqual(response.status_code, 400)
            self.assertIn("error", response.get_json())

    def test_timezone_day_boundary(self):
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 18, 18, 1, tzinfo=timezone.utc).astimezone(tz)
        with patch("app.datetime", FixedDatetime):
            self.assertEqual(self.client.get("/api/daily").get_json()["date"], "2026-10-19")

    def test_invalid_catalog_returns_actionable_503_not_fake_content(self):
        with self.assertLogs(self.app.logger, level="ERROR"), patch("app.load_catalog", side_effect=ValueError("Broken private file details")):
            for endpoint in ("/api/catalog", "/api/daily", "/health"):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(b"private file details", response.data)

    def test_invalid_timezone_reports_unhealthy(self):
        invalid_app = create_app({"TESTING": True, "LEXI_TIMEZONE": "Not/A_Zone"})
        with self.assertLogs(invalid_app.logger, level="ERROR"):
            self.assertEqual(invalid_app.test_client().get("/health").status_code, 503)

    def test_pwa_and_local_assets_are_served_with_correct_content(self):
        manifest = self.client.get("/manifest.webmanifest")
        self.addCleanup(manifest.close)
        self.assertEqual(manifest.status_code, 200)
        for entry in manifest.get_json()["icons"]:
            with self.client.get(entry["src"]) as response:
                self.assertEqual(response.status_code, 200)
        worker = self.client.get("/sw.js")
        self.addCleanup(worker.close)
        self.assertIn("javascript", worker.content_type)
        self.assertIn(b"/api/catalog", worker.data)
        for asset in ("css/style.css", "js/app.js", "js/selection.js", "fonts/Syne.ttf", "fonts/DMSans.ttf"):
            with self.client.get("/static/" + asset) as response:
                self.assertEqual(response.status_code, 200)

    def test_response_security_and_fresh_daily_cache_headers(self):
        response = self.client.get("/api/daily")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()
