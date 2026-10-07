"""CRAN and Bioconductor, which nixpkgs' rPackages are generated from
(pkgs/development/r-modules: generate-r-packages.R reads the same index
files R does, CRAN's as it is that day, and Bioconductor's for the release
nixpkgs pins). Each run reads which Bioconductor release nixpkgs pins (the
top of bioc-packages.json on nixpkgs master: "biocVersion": "3.23", a few
bytes of it), and the four indexes (their PACKAGES.gz; five requests),
written to data/cran.json.gz:

    {"format": 1, "fetchedAt": "2026-10-08T04:10:00+00:00",
     "biocVersion": "3.23",
     "cran": {"ggplot2": "4.0.1", ...}, "bioc": {...},
     "annotation": {...}, "experiment": {...}}

A package nixpkgs has in none of them is no longer on CRAN (archived) or
in that Bioconductor release. A run that can't read all of them keeps the
last file (its fetchedAt says how old it is)."""

import gzip
import json
import os
import re
import sys
import urllib.error

from . import download

FILE = "cran.json.gz"
FORMAT = 1
NIXPKGS_BIOC = (
    "https://raw.githubusercontent.com/NixOS/nixpkgs/master/pkgs/development/"
    "r-modules/bioc-packages.json"
)
BIOC_VERSION = re.compile(r'"biocVersion"\s*:\s*"([0-9.]+)"')
BIOC = "https://bioconductor.org/packages/{bioc}/"
# Each index: where it is, and the fewest packages it should have (about
# two-thirds of 2026-10-07's: 25,353, 2,384, 928, 434).
INDEXES = {
    "cran": ("https://cran.r-project.org/src/contrib/PACKAGES.gz", 15000),
    "bioc": (BIOC + "bioc/src/contrib/PACKAGES.gz", 1500),
    "annotation": (BIOC + "data/annotation/src/contrib/PACKAGES.gz", 600),
    "experiment": (BIOC + "data/experiment/src/contrib/PACKAGES.gz", 250),
}
# A PACKAGES file: one paragraph per package, "Field: value" lines.
PACKAGE = re.compile(r"^Package:\s*(\S+)", re.MULTILINE)
VERSION = re.compile(r"^Version:\s*(\S+)", re.MULTILINE)


def pinned(text):
    """The Bioconductor release nixpkgs pins, from the top of its
    bioc-packages.json. Raises when it doesn't say."""
    found = BIOC_VERSION.search(text)
    if not found:
        raise ValueError("bioc-packages.json doesn't say which Bioconductor release")
    return found.group(1)


def packages(text):
    """{package: version} from a PACKAGES file."""
    found = {}
    for paragraph in re.split(r"\n\s*\n", text):
        name, version = PACKAGE.search(paragraph), VERSION.search(paragraph)
        if name and version:
            found[name.group(1)] = version.group(1)
    return found


def read_indexes():
    """{"biocVersion", "cran", "bioc", "annotation", "experiment"}: what write
    writes. Raises when one can't be read or has too few packages."""
    top = download.get(NIXPKGS_BIOC, first_bytes=200).decode("utf-8", "replace")
    bioc = pinned(top)
    found = {"biocVersion": bioc}
    for index, (url, least) in INDEXES.items():
        body = gzip.decompress(download.get(url.format(bioc=bioc)))
        found[index] = dict(sorted(packages(body.decode("utf-8", "replace")).items()))
        if len(found[index]) < least:
            raise ValueError(
                f"only {len(found[index]):,} packages in {index} (expected over "
                f"{least:,})"
            )
    return found


def write(directory, found, now):
    os.makedirs(directory, exist_ok=True)
    body = {"format": FORMAT, "fetchedAt": now.isoformat(timespec="seconds"), **found}
    data = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    with open(os.path.join(directory, FILE), "wb") as f:
        f.write(gzip.compress(data, compresslevel=9, mtime=0))


def read(directory):
    """cran.json.gz in directory, or None if there's none."""
    try:
        with gzip.open(os.path.join(directory, FILE), "rt") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def update(directory, now):
    """Bring cran.json.gz up to date: {"at", "biocVersion", index: packages,
    ...} for meta.json, or None when it couldn't be read (the last file stays,
    with a warning: the Repology digest goes on regardless)."""
    print("Reading CRAN and Bioconductor...", file=sys.stderr)
    try:
        found = read_indexes()
    except (urllib.error.URLError, OSError, ValueError, EOFError) as e:
        print(f"::warning::CRAN and Bioconductor: {e}; kept the last", file=sys.stderr)
        return None
    write(directory, found, now)
    return {
        "at": now.isoformat(timespec="seconds"),
        "biocVersion": found["biocVersion"],
        **{index: len(found[index]) for index in INDEXES},
    }
