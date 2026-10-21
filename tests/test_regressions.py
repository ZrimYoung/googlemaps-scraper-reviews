"""Offline regressions: exercise the scraper with deterministic browser pages."""
import contextlib
import csv
import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main as scraper
import batch_scraper as batch
import process_urls
from retry_failed_scrapes import FailedScrapeRetryProcessor
from url_utils import english_maps_url
from urllib.parse import parse_qs, urlsplit
from selenium.common.exceptions import NoSuchElementException, TimeoutException


class Element:
    def __init__(self, text="", attrs=None, children=None):
        self.text = text
        self.attrs = attrs or {}
        self.children = children or {}

    def get_attribute(self, name):
        return self.attrs.get(name)

    def find_elements(self, by, selector):
        return self.children.get(selector, [])

    def find_element(self, by, selector):
        elements = self.find_elements(by, selector)
        if not elements:
            raise NoSuchElementException(selector)
        return elements[0]

    def is_displayed(self):
        return True


def review(identity="r1", content="Good", rating="2 stars"):
    children = {
        "span.kvMYJc": [Element(attrs={"aria-label": rating})],
        "span.rsqaWe": [Element("a month ago")],
    }
    if content is not None:
        children["span.wiI7pd"] = [Element(content)]
    return Element(attrs={"aria-label": "Alice", "data-review-id": identity}, children=children)


class Browser:
    def __init__(self, pages=None, button=True, expected=1, name="Shop"):
        self.pages = pages if pages is not None else [[review()]]
        self.page = 0
        self.button = button
        self.expected = expected
        self.name = name
        self.current_url = "https://www.google.com/maps/place/Shop/@22.3,114.2,17z"
        self.closed = False

    def get(self, url):
        self.loaded_url = url

    def set_page_load_timeout(self, timeout):
        pass

    def quit(self):
        self.closed = True

    def execute_script(self, script, element):
        if script.startswith("return"):
            return 1000  # Virtualized lists can retain a fixed height.
        if "scrollTop" in script:
            self.page = min(self.page + 1, len(self.pages) - 1)

    def find_elements(self, by, selector):
        if selector == "div.jftiEf.fontBodyMedium":
            return self.pages[self.page]
        if selector == "h1.DUwDvf.lfPIob":
            return [Element(self.name)] if self.name else []
        if selector == "span.ceNzKf":
            return [Element(attrs={"aria-label": "4.5 stars"})]
        if selector == "button.DkEaL":
            return [Element("Cafe")]
        if selector == "button[aria-label]":
            return [] if self.expected is None else [Element(attrs={"aria-label": f"{self.expected:,} reviews"})]
        if selector.startswith("//"):
            if "No reviews" in selector:
                return [Element("No reviews")] if self.expected == 0 else []
            return [Element("Reviews")] if self.button else []
        if selector.startswith("div.m6QErb"):
            return [Element()]
        return []

    def find_element(self, by, selector):
        elements = self.find_elements(by, selector)
        if not elements:
            raise NoSuchElementException(selector)
        return elements[0]


class ImmediateWait:
    """Deterministic replacement for Selenium polling in offline tests."""
    def __init__(self, *args, **kwargs):
        self.driver = args[0]

    def until(self, condition):
        try:
            result = condition(self.driver)
        except NoSuchElementException:
            result = False
        if not result:
            raise TimeoutException()
        return result


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def scrape(self, browser=None, **kwargs):
        browser = browser or Browser()
        with patch.object(scraper.webdriver, "Chrome", return_value=browser), \
                patch.object(scraper, "WebDriverWait", ImmediateWait), \
                patch.object(scraper.time, "sleep"):
            result = scraper.scrape_single_url(browser.current_url, str(self.output), max_retries=1, **kwargs)
        self.assertTrue(browser.closed)
        return result

    def processor(self):
        with patch.object(batch.BatchGoogleMapsScraper, "setup_logging", lambda s: setattr(s, "logger", logging.getLogger("test"))):
            return batch.BatchGoogleMapsScraper(output_base_dir=str(self.output))

    def test_csv_keeps_review_rating_separate_from_business_rating(self):
        result = self.scrape()
        with open(result["csv_file"], encoding="utf-8-sig", newline="") as file:
            row = next(csv.DictReader(file))
        self.assertEqual(row["rating"], "2 stars")
        self.assertEqual(row["business_rating"], "4.5 stars")

    def test_rating_only_review_is_retained(self):
        result = self.scrape(Browser(pages=[[review(content=None)]]))
        self.assertEqual(result["reviews_count"], 1)
        self.assertEqual(result["reviews"][0]["content"], "")

    def test_missing_reviews_button_is_failure(self):
        result = self.scrape(Browser(button=False))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], 1004)

    def test_batch_does_not_treat_error_1004_as_success(self):
        response = {"success": True, "error_code": 1004, "reviews_count": 0}
        with patch.object(batch.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps([response]))):
            result = self.processor().scrape_single_place({"place_id": "p1", "Maps_url": "https://example.com"})
        self.assertFalse(result["final_success"])

    def test_changing_review_ids_with_constant_height_are_collected(self):
        browser = Browser(pages=[[review(f"r{i}")] for i in range(8)], expected=8)
        result = self.scrape(browser)
        self.assertEqual(result["reviews_count"], 8)

    def test_documented_url_field_is_accepted(self):
        path = self.output / "input.jsonl"
        path.write_text(json.dumps({"place_id": "p1", "url": "https://maps.google.com/?cid=1", "parent_type": "food", "sub_type": "cafe"}) + "\n")
        places = self.processor().load_jsonl_input(str(path))
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["Maps_url"], "https://maps.google.com/?cid=1&hl=en")

    def test_documented_single_url_and_no_headless_are_accepted(self):
        result = {"success": True, "business_info": {"name": "Shop"}, "reviews_count": 1}
        with patch("sys.argv", ["main.py", "https://maps.google.com/?cid=1", "--no-headless", "--json-output"]), \
                patch.object(scraper, "scrape_single_url", return_value=result) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            scraper.main()
        self.assertFalse(run.call_args.args[2])

    def test_limit_keeps_partial_data_and_reports_incomplete(self):
        browser = Browser(pages=[[review(f"r{i}")] for i in range(10)], expected=10)
        result = self.scrape(browser, max_scrolls=2)
        self.assertFalse(result["success"])
        self.assertFalse(result["reviews_complete"])
        self.assertEqual(result["error_code"], 1011)
        self.assertEqual(result["review_stop_reason"], "max_scrolls")
        self.assertEqual(result["reviews_count"], 3)
        self.assertEqual(result["expected_review_count"], 10)

    def test_unknown_count_never_claims_completeness(self):
        result = self.scrape(Browser(expected=None))
        self.assertFalse(result["success"])
        self.assertEqual(result["reviews_count"], 1)
        self.assertEqual(result["review_stop_reason"], "stalled")

    def test_explicit_zero_reviews_is_success(self):
        result = self.scrape(Browser(expected=0, pages=[[]], button=False))
        self.assertTrue(result["success"])
        self.assertTrue(result["reviews_complete"])
        self.assertEqual(result["reviews_count"], 0)
        self.assertEqual(result["review_stop_reason"], "no_reviews")

    def test_expected_count_reached_and_duplicates_removed(self):
        browser = Browser(pages=[[review()], [review(), review("r2")]], expected=2)
        result = self.scrape(browser)
        self.assertTrue(result["success"])
        self.assertEqual(result["reviews_count"], 2)
        self.assertEqual(result["review_stop_reason"], "expected_count_reached")

    def test_broken_review_markup_is_not_empty_success(self):
        broken = Element(attrs={"data-review-id": "broken"})
        result = self.scrape(Browser(pages=[[broken]], expected=1))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], 1006)

    def test_missing_business_identity_is_failure(self):
        result = self.scrape(Browser(name=""))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], 1003)

    def test_successful_retry_clears_previous_error(self):
        first, second = Browser(button=False), Browser()
        with patch.object(scraper.webdriver, "Chrome", side_effect=[first, second]), \
                patch.object(scraper, "WebDriverWait", ImmediateWait), \
                patch.object(scraper.time, "sleep"):
            result = scraper.scrape_single_url(second.current_url, str(self.output), max_retries=2)
        self.assertTrue(first.closed and second.closed)
        self.assertTrue(result["success"])
        self.assertEqual(result["error_code"], 0)
        self.assertEqual(result["error_message"], "")

    def test_csv_failure_is_not_success(self):
        with patch.object(scraper.pd.DataFrame, "to_csv", side_effect=OSError("disk full")):
            result = self.scrape()
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], 1008)

    def test_batch_requires_complete_error_free_result(self):
        for response, expected_success in [
            ({"success": True, "error_code": 1008, "reviews_count": 1, "reviews_complete": True}, False),
            ({"success": True, "error_code": 0, "reviews_count": 1, "reviews_complete": False}, False),
            ({"success": True, "error_code": 0, "reviews_count": 1, "reviews_complete": True}, True),
            ({"success": True, "error_code": 0, "reviews_count": 0, "reviews_complete": True}, True),
        ]:
            with self.subTest(response=response), patch.object(batch.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps([response]))):
                result = self.processor().scrape_single_place({"place_id": "p1", "Maps_url": "https://example.com"})
            self.assertEqual(result["final_success"], expected_success)

    def test_incomplete_result_is_saved_as_failed_and_retried(self):
        place = {"place_id": "p1", "Maps_url": "https://maps.google.com/?cid=1", "parent_type": "food", "sub_type": "cafe"}
        response = self.scrape(Browser(expected=10), max_scrolls=1)
        processor = self.processor()
        with patch.object(batch.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps([response]))):
            processor.process_batch([place], max_workers=1)
        progress = processor.load_progress()
        self.assertIn("p1", progress["failed"])
        self.assertNotIn("p1", progress["successful"])
        scanner = FailedScrapeRetryProcessor.__new__(FailedScrapeRetryProcessor)
        scanner.output_dir, scanner.logger = self.output, logging.getLogger("test")
        records = scanner.scan_failed_files()
        self.assertEqual([record["place_id"] for record in records], ["p1"])

    def test_retry_scanner_finds_legacy_false_success(self):
        path = self.output / "food" / "cafe"
        path.mkdir(parents=True)
        (path / "p1.json").write_text(json.dumps({
            "place_id": "p1", "Maps_url": "https://maps.google.com/?cid=1",
            "scrape_success": True, "final_success": True, "scrape_error_code": 1004,
        }))
        scanner = FailedScrapeRetryProcessor.__new__(FailedScrapeRetryProcessor)
        scanner.output_dir, scanner.logger = self.output, logging.getLogger("test")
        self.assertEqual(len(scanner.scan_failed_files()), 1)

    def test_url_normalization_preserves_query_and_fragment(self):
        for url in ["https://maps.google.com/place/test", "https://maps.google.com/?cid=1&hl=zh-CN#map", "https://maps.google.com/?q=A%26B&hl=zh&hl=fr&empty=#map"]:
            with self.subTest(url=url):
                normalized = english_maps_url(url)
                self.assertEqual(parse_qs(urlsplit(normalized).query)["hl"], ["en"])
                self.assertEqual(urlsplit(normalized).fragment, urlsplit(url).fragment)
                self.assertEqual(english_maps_url(normalized), normalized)
        self.assertEqual(parse_qs(urlsplit(english_maps_url(url)).query)["q"], ["A&B"])

    def test_url_preprocessor_supports_both_keys_and_bom(self):
        source, destination = self.output / "source.jsonl", self.output / "result.jsonl"
        source.write_text('\ufeff' + json.dumps({"url": "https://maps.google.com/?hl=zh"}) + '\n' + json.dumps({"Maps_url": "https://maps.google.com/place/test"}) + '\n', encoding="utf-8")
        process_urls.process_urls(source, destination)
        rows = [json.loads(line) for line in destination.read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["url"], rows[0]["Maps_url"])
        self.assertTrue(all(parse_qs(urlsplit(row["Maps_url"]).query)["hl"] == ["en"] for row in rows))

    def test_batch_documented_modes_resume_and_overrides(self):
        for mode, workers, places, retries, timeout in [("--test", 1, 5, 2, 60), ("--production", 5, 1000, 5, 600)]:
            with self.subTest(mode=mode), patch("sys.argv", ["batch_scraper.py", "input.jsonl", mode, "--resume", "--max-scrolls", "60"]), \
                    patch.object(batch, "BatchGoogleMapsScraper") as factory:
                factory.return_value.load_jsonl_input.return_value = [{"place_id": "p1"}]
                batch.main()
                options = factory.return_value.process_batch.call_args.kwargs
                self.assertEqual((options["max_workers"], options["max_places"], options["max_retries"], options["timeout"]), (workers, places, retries, timeout))
                self.assertTrue(options["resume"])
                self.assertEqual(options["max_scrolls"], 60)
        with patch("sys.argv", ["batch_scraper.py", "input.jsonl", "--test", "--max-workers", "2", "--timeout", "90", "--no-resume"]), patch.object(batch, "BatchGoogleMapsScraper") as factory:
            factory.return_value.load_jsonl_input.return_value = [{"place_id": "p1"}]
            batch.main()
            options = factory.return_value.process_batch.call_args.kwargs
            self.assertEqual(options["max_workers"], 2)
            self.assertEqual(options["timeout"], 90)
            self.assertFalse(options["resume"])

    def test_batch_forwards_scroll_settings_to_child_process(self):
        response = {"success": True, "error_code": 0, "reviews_count": 1, "reviews_complete": True}
        with patch.object(batch.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps([response]))) as run:
            self.processor().scrape_single_place({"place_id": "p1", "Maps_url": "https://example.com"}, max_scrolls=60, scroll_wait=5)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--max-scrolls") + 1], "60")
        self.assertEqual(command[command.index("--scroll-wait") + 1], "5")

    def test_normal_cli_reports_correct_success_count(self):
        result = {"success": True, "business_info": {"name": "Shop"}, "reviews_count": 1}
        output = io.StringIO()
        with patch("sys.argv", ["main.py", "--url", "https://maps.google.com/?cid=1"]), patch.object(scraper, "scrape_single_url", return_value=result), contextlib.redirect_stdout(output):
            scraper.main()
        self.assertIn("成功: 1/1", output.getvalue())

    def test_no_resume_reprocesses_selected_place_and_clears_old_success(self):
        processor = self.processor()
        progress = processor.load_progress()
        progress['successful'] = ['p1', 'unrelated']
        processor.save_progress(progress)
        place = {"place_id": "p1", "Maps_url": "https://maps.google.com/?cid=1", "parent_type": "food", "sub_type": "cafe"}
        response = {"success": False, "error_code": 1004, "reviews_count": 0}
        with patch.object(batch.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps([response]))) as run:
            processor.process_batch([place], max_workers=1, resume=False)
        self.assertEqual(run.call_count, 1)
        progress = processor.load_progress()
        self.assertEqual(progress['successful'], ['unrelated'])
        self.assertEqual(progress['failed'], ['p1'])

    def test_scroll_error_preserves_already_collected_reviews(self):
        browser = Browser(expected=10)
        original = browser.execute_script

        def execute(script, element):
            if 'scrollTop' in script:
                raise scraper.WebDriverException('disconnected')
            return original(script, element)

        with patch.object(browser, 'execute_script', side_effect=execute):
            result = self.scrape(browser)
        self.assertFalse(result['success'])
        self.assertEqual(result['error_code'], 1005)
        self.assertEqual(result['reviews_count'], 1)

    def test_readme_examples_match_real_result_fields(self):
        import re
        readme = (Path(__file__).resolve().parents[1] / 'README.md').read_text()
        examples = [json.loads(block) for block in re.findall(r'```json\n(.*?)\n```', readme, re.S)]
        actual = self.scrape()
        for example in examples:
            if 'business_info' not in example:
                continue
            self.assertEqual(set(example['business_info']), set(actual['business_info']))
            self.assertEqual(set(example['reviews'][0]), set(actual['reviews'][0]))
            self.assertEqual(example['reviews_count'], len(example['reviews']))


if __name__ == "__main__":
    unittest.main()
