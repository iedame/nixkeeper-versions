import io
import json
import tempfile
import unittest
from datetime import UTC, datetime
from unittest import mock

from nixkeeper_versions import emacs

NOW = datetime(2026, 10, 8, 4, 10, tzinfo=UTC)

# Trimmed from the archives' indexes (2026-10-07).
MELPA = json.dumps(
    {
        "0blayout": {"ver": [20190703, 527], "deps": None, "type": "tar"},
        "magit": {"ver": [20251001, 1200], "props": {"commit": "abc"}},
    }
).encode()
MELPA_STABLE = json.dumps({"magit": {"ver": [4, 4, 2]}}).encode()
GNU = b"""(1
 (a68-mode
  . [(1 3) ((emacs (24 3))) "Major mode for editing Algol 68 code" tar
     ((:url . "https://git.sr.ht/~jemarch/a68-mode")
      (:maintainer "Jose E. Marchesi" . "jemarch@gnu.org")
      (:commit . "a35b2fec07dcf9c3550cebc7f75e13f240088db2"))])
 (ace-window
  . [(0 10 0) ((avy (0 5 0))) "Quickly switch windows" tar
     ((:url . "https://github.com/abo-abo/ace-window"))])
 (beta-thing . [(1 0 -2 3) nil "A beta" tar nil]))
"""
NONGNU = b"""(1 (jabber . [(0 15 0) ((emacs (27 1))) "XMPP client" tar nil]))"""
BODIES = {
    "https://melpa.org/archive.json": MELPA,
    "https://stable.melpa.org/archive.json": MELPA_STABLE,
    "https://elpa.gnu.org/packages/archive-contents": GNU,
    "https://elpa.nongnu.org/nongnu/archive-contents": NONGNU,
}


class Parse(unittest.TestCase):
    def test_melpa(self):
        self.assertEqual(
            emacs.from_json(MELPA),
            {"0blayout": "20190703.527", "magit": "20251001.1200"},
        )

    def test_elpa(self):
        # Only entries' names and versions: not the dependencies' ((avy (0 5
        # 0))), nor the header's 1, nor the keywords.
        self.assertEqual(
            emacs.from_elisp(GNU),
            {"a68-mode": "1.3", "ace-window": "0.10.0", "beta-thing": "1.0beta3"},
        )

    def test_joined_as_emacs_writes_them(self):
        self.assertEqual(emacs.joined([1, 0, -2, 3]), "1.0beta3")
        self.assertEqual(emacs.joined([2, -4]), "2snapshot")
        self.assertEqual(emacs.joined([20251001, 1200]), "20251001.1200")


class Update(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("sys.stderr", io.StringIO())
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(
            emacs.ARCHIVES,
            {k: (url, kind, 1) for k, (url, kind, _) in emacs.ARCHIVES.items()},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def serve(self, bodies):
        def get(url):
            if bodies.get(url) is None:
                raise OSError(f"{url}: down")
            return bodies[url]

        return mock.patch.object(emacs.download, "get", side_effect=get)

    def test_written_and_read(self):
        with tempfile.TemporaryDirectory() as d, self.serve(BODIES):
            self.assertEqual(
                emacs.update(d, NOW),
                {
                    "at": "2026-10-08T04:10:00+00:00",
                    "melpa": 2,
                    "melpaStable": 1,
                    "nongnu": 1,
                    "gnu": 3,
                },
            )
            found = emacs.read(d)
        self.assertEqual(found["fetchedAt"], "2026-10-08T04:10:00+00:00")
        self.assertEqual(found["archives"]["melpa"]["magit"], "20251001.1200")
        self.assertEqual(found["archives"]["nongnu"], {"jabber": "0.15.0"})

    def test_the_last_stays_when_an_archive_fails(self):
        with tempfile.TemporaryDirectory() as d:
            with self.serve(BODIES):
                emacs.update(d, NOW)
            before = emacs.read(d)
            down = {**BODIES, "https://elpa.gnu.org/packages/archive-contents": None}
            with self.serve(down):
                self.assertIsNone(emacs.update(d, NOW))
            self.assertEqual(emacs.read(d), before)

    def test_too_few_packages_is_not_the_index(self):
        with (
            tempfile.TemporaryDirectory() as d,
            self.serve(BODIES),
            mock.patch.dict(
                emacs.ARCHIVES, {"melpa": ("https://melpa.org/archive.json", "json", 5)}
            ),
        ):
            self.assertIsNone(emacs.update(d, NOW))
            self.assertIsNone(emacs.read(d))


if __name__ == "__main__":
    unittest.main()
