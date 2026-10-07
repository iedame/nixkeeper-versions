import gzip
import io
import tempfile
import unittest
from datetime import UTC, datetime
from unittest import mock

from nixkeeper_versions import cran

NOW = datetime(2026, 10, 8, 4, 10, tzinfo=UTC)

# Trimmed from nixpkgs' bioc-packages.json (its top) and the indexes'
# PACKAGES files (2026-10-07).
TOP = (
    b'{\n  "extraArgs": {\n    "biocVersion": "3.23"\n  },\n'
    b'  "packages": {\n    "ABSSeq": {'
)
CRAN = b"""Package: A3
Version: 1.0.0
Depends: R (>= 2.15.0), xtable, pbapply
License: GPL (>= 2)
NeedsCompilation: no

Package: ggplot2
Version: 4.0.1
Imports: cli, grDevices,
        grid, gtable (>= 0.3.6)
License: MIT + file LICENSE

Package: abc.data
Version: 1.1
"""
BIOC = b"""Package: AnVIL
Version: 1.24.1

Package: BatchQC
Version: 2.8.3
"""
BIOC_URL = "https://bioconductor.org/packages/3.23/"
BODIES = {
    cran.NIXPKGS_BIOC: TOP,
    "https://cran.r-project.org/src/contrib/PACKAGES.gz": gzip.compress(CRAN),
    BIOC_URL + "bioc/src/contrib/PACKAGES.gz": gzip.compress(BIOC),
    BIOC_URL + "data/annotation/src/contrib/PACKAGES.gz": gzip.compress(
        b"Package: org.Hs.eg.db\nVersion: 3.22.0\n"
    ),
    BIOC_URL + "data/experiment/src/contrib/PACKAGES.gz": gzip.compress(
        b"Package: ALL\nVersion: 1.52.0\n"
    ),
}


class Parse(unittest.TestCase):
    def test_the_release_nixpkgs_pins(self):
        self.assertEqual(cran.pinned(TOP.decode()), "3.23")
        with self.assertRaises(ValueError):
            cran.pinned('{"packages": {')

    def test_packages(self):
        # Continuation lines and other fields aren't versions.
        self.assertEqual(
            cran.packages(CRAN.decode()),
            {"A3": "1.0.0", "ggplot2": "4.0.1", "abc.data": "1.1"},
        )


class Update(unittest.TestCase):
    def setUp(self):
        for patcher in (
            mock.patch("sys.stderr", io.StringIO()),
            mock.patch.dict(
                cran.INDEXES, {k: (url, 1) for k, (url, _) in cran.INDEXES.items()}
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def serve(self, bodies):
        asked = []

        def get(url, first_bytes=None):
            asked.append((url, first_bytes))
            if bodies.get(url) is None:
                raise OSError(f"{url}: down")
            return bodies[url]

        return mock.patch.object(cran.download, "get", side_effect=get), asked

    def test_written_and_read(self):
        served, asked = self.serve(BODIES)
        with tempfile.TemporaryDirectory() as d, served:
            self.assertEqual(
                cran.update(d, NOW),
                {
                    "at": "2026-10-08T04:10:00+00:00",
                    "biocVersion": "3.23",
                    "cran": 3,
                    "bioc": 2,
                    "annotation": 1,
                    "experiment": 1,
                },
            )
            found = cran.read(d)
        self.assertEqual(found["biocVersion"], "3.23")
        self.assertEqual(found["bioc"], {"AnVIL": "1.24.1", "BatchQC": "2.8.3"})
        # Only the top of nixpkgs' bioc-packages.json.
        self.assertEqual(asked[0], (cran.NIXPKGS_BIOC, 200))

    def test_the_last_stays(self):
        with tempfile.TemporaryDirectory() as d:
            served, _ = self.serve(BODIES)
            with served:
                cran.update(d, NOW)
            before = cran.read(d)
            down = {
                **BODIES,
                "https://cran.r-project.org/src/contrib/PACKAGES.gz": None,
            }
            served, _ = self.serve(down)
            with served:
                self.assertIsNone(cran.update(d, NOW))
            served, _ = self.serve(BODIES)
            with (
                served,
                mock.patch.dict(
                    cran.INDEXES,
                    {"cran": ("https://cran.r-project.org/src/contrib/PACKAGES.gz", 5)},
                ),
            ):
                self.assertIsNone(cran.update(d, NOW))  # 3 < 5: not the index
            self.assertEqual(cran.read(d), before)


if __name__ == "__main__":
    unittest.main()
