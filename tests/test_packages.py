import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

from nixkeeper_versions import packages, releases

NOW = datetime(2026, 10, 8, 4, 10, tzinfo=UTC)
INDEX = {
    "python313Packages.requests": {"pname": "requests", "version": "2.32.5"},
    "ripgrep": {"pname": "ripgrep", "version": "15.1.0", "meta": {"x": 1}},
    "hello": {"pname": "hello", "version": ""},  # empty fields left out
}
RIPGREP = {
    "version": "15.1.0",
    "gitRepoUrl": "https://github.com/BurntSushi/ripgrep.git",
    "tag": "15.1.0",
    "rev": None,
    "url": "https://github.com/BurntSushi/ripgrep/archive/refs/tags/15.1.0.tar.gz",
}


def update(d, now=NOW, evaluated=None, load=lambda: INDEX):
    with mock.patch.object(packages, "MIN_PACKAGES", 1):
        return packages.update(d, now, evaluated, load=load, revision=lambda: "abc")


class Packages(unittest.TestCase):
    def test_index_then_sources(self):
        with tempfile.TemporaryDirectory() as d:
            meta = update(d)
            got = packages.read(d)
            self.assertEqual(got["revision"], "abc")
            self.assertEqual(
                got["packages"]["python313Packages.requests"],
                {"pname": "requests", "version": "2.32.5"},
            )
            self.assertEqual(got["packages"]["hello"], {"pname": "hello"})
            self.assertEqual((meta["packages"], meta["sources"]), (3, 0))
            # The weekly evaluation: each source with the fields it has.
            update(d, NOW + timedelta(hours=1), ("def", {"ripgrep": RIPGREP}))
            got = packages.read(d)
            self.assertEqual(
                got["packages"]["ripgrep"]["src"],
                {k: RIPGREP[k] for k in ("gitRepoUrl", "tag", "url")},
            )
            self.assertEqual(got["evaluatedRevision"], "def")

    def test_index_daily_sources_kept(self):
        with tempfile.TemporaryDirectory() as d:
            update(d, evaluated=("def", {"ripgrep": RIPGREP}))
            loads = []

            def load():
                loads.append(1)
                return INDEX

            update(d, NOW + timedelta(hours=2), load=load)
            self.assertEqual(loads, [])  # read this morning already
            update(d, NOW + timedelta(days=1), load=load)
            self.assertEqual(loads, [1])
            # No evaluation this run: last week's sources stay.
            self.assertIn("src", packages.read(d)["packages"]["ripgrep"])

    def test_a_failed_read_keeps_the_last(self):
        with tempfile.TemporaryDirectory() as d:
            update(d)

            def down():
                raise OSError("no answer")

            update(d, NOW + timedelta(days=1), load=down)
            got = packages.read(d)
            self.assertEqual(len(got["packages"]), 3)
            self.assertEqual(got["indexedAt"], NOW.isoformat(timespec="seconds"))

    def test_a_short_index_isnt_written(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(packages.update(d, NOW, load=lambda: INDEX, revision=str))
            self.assertIsNone(packages.read(d))


class Evaluated(unittest.TestCase):
    def test_every_src_handed_over(self):
        def sources(attrs, revision):
            return {a: {"version": "1", "url": f"https://x/{a}"} for a in attrs}

        found = {}
        with mock.patch.object(releases.nixpkgs, "sources", side_effect=sources):
            releases.evaluate("abc", ["a", "b"], found)
        self.assertEqual(set(found), {"a", "b"})
