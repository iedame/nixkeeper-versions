"""The Emacs package archives nixpkgs' emacsPackages are made from, which
Repology mostly can't compare (MELPA's versions are dates: "untrusted"):
the newest version of each package in each archive, from their indexes
(the ones nixpkgs' own update scripts read; one request each), written to
data/emacs.json.gz:

    {"format": 1, "fetchedAt": "2026-10-08T04:10:00+00:00",
     "archives": {"melpa": {"magit": "20251001.1200", ...},
                  "melpaStable": {"magit": "4.4.2", ...},
                  "nongnu": {...}, "gnu": {...}}}

MELPA's versions are the date and time of the commit it built
("20251001.1200"); the others, releases. A run that can't read every
archive, or reads one with too few packages, keeps the last file (its
fetchedAt says how old it is)."""

import gzip
import json
import os
import re
import sys
import urllib.error

from . import download

FILE = "emacs.json.gz"
FORMAT = 1
# Each archive: where its index is, how it's written, and the fewest
# packages it should have (about two-thirds of 2026-10-07's: 6,331,
# 3,488, 291, 508); fewer, it's not the index it should be.
ARCHIVES = {
    "melpa": ("https://melpa.org/archive.json", "json", 4000),
    "melpaStable": ("https://stable.melpa.org/archive.json", "json", 2000),
    "nongnu": ("https://elpa.nongnu.org/nongnu/archive-contents", "elisp", 150),
    "gnu": ("https://elpa.gnu.org/packages/archive-contents", "elisp", 300),
}
# Emacs' words for a negative version part (version-regexp-alist), as
# package-version-join writes them: (1 0 -2 3) is "1.0beta3".
NEGATIVE = {-1: "pre", -2: "beta", -3: "alpha", -4: "snapshot"}
# An entry of an ELPA archive-contents (Emacs Lisp data): "(name . [(1 3)
# ((emacs (24 3))) "description" tar ...])": its name and version list.
ELPA_ENTRY = re.compile(r"\(\s*([^\s()\"]+)\s*\.\s*\[\s*\(([-\d\s]*)\)")


def joined(parts):
    """A version list as Emacs writes it (package-version-join): numbers
    joined by dots, a negative one as its word ((1 0 -2 3): "1.0beta3")."""
    text = ""
    for part in parts:
        if part < 0:
            text += NEGATIVE.get(part, "snapshot")
        else:
            text += ("." if text and text[-1].isdigit() else "") + str(part)
    return text


def from_json(body):
    """{name: version} from a MELPA archive.json ({"magit": {"ver": [20251001,
    1200], ...}, ...})."""
    return {
        name: joined(entry["ver"])
        for name, entry in json.loads(body).items()
        if entry.get("ver")
    }


def from_elisp(body):
    """{name: version} from an ELPA archive-contents: "(1 (a68-mode . [(1 3)
    ...]) (ace-window . [(0 10 0) ...]) ...)". Only each entry's name and
    version are read, with a pattern: nothing else of it is needed."""
    text = body.decode("utf-8", "replace")
    return {
        name: joined(int(n) for n in version.split())
        for name, version in ELPA_ENTRY.findall(text)
        if version.split()
    }


def read_archives():
    """{archive: {name: version}} for every archive in ARCHIVES. Raises when
    one can't be read or has too few packages."""
    found = {}
    for archive, (url, kind, least) in ARCHIVES.items():
        body = download.get(url)
        packages = from_json(body) if kind == "json" else from_elisp(body)
        if len(packages) < least:
            raise ValueError(
                f"only {len(packages):,} packages in {archive} (expected over "
                f"{least:,})"
            )
        found[archive] = dict(sorted(packages.items()))
    return found


def write(directory, archives, now):
    """Write emacs.json.gz (archives: read_archives') to directory."""
    os.makedirs(directory, exist_ok=True)
    body = {
        "format": FORMAT,
        "fetchedAt": now.isoformat(timespec="seconds"),
        "archives": archives,
    }
    data = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    with open(os.path.join(directory, FILE), "wb") as f:
        f.write(gzip.compress(data, compresslevel=9, mtime=0))


def read(directory):
    """emacs.json.gz in directory, or None if there's none."""
    try:
        with gzip.open(os.path.join(directory, FILE), "rt") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def update(directory, now):
    """Bring emacs.json.gz up to date: {"at", archive: packages, ...} for
    meta.json, or None when an archive couldn't be read (the last file
    stays, with a warning: the Repology digest goes on regardless)."""
    print("Reading the Emacs package archives...", file=sys.stderr)
    try:
        archives = read_archives()
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"::warning::Emacs archives: {e}; kept the last", file=sys.stderr)
        return None
    write(directory, archives, now)
    return {
        "at": now.isoformat(timespec="seconds"),
        **{archive: len(packages) for archive, packages in archives.items()},
    }
