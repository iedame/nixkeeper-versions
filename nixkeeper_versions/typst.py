"""Typst Universe (https://typst.app/universe/), the source of nixpkgs'
typstPackages, which Repology mostly can't compare: the newest version of
each of its packages, from its index (one request, 2.3 MB, every version
of every package), written to data/typst.json.gz:

    {"format": 1, "fetchedAt": "2026-10-07T04:10:00+00:00",
     "packages": {"cetz": {"version": "0.5.2", "released": "2026-09-30"}, ...}}

A run that can't read the index, or reads one with too few packages, keeps
the last file (its fetchedAt says how old it is)."""

import gzip
import json
import os
import sys
import urllib.error
from datetime import UTC, datetime

from . import download

INDEX = "https://packages.typst.org/preview/index.json"
FILE = "typst.json.gz"
FORMAT = 1
# Fewer packages than this (about 1,650 on 2026-10-07): not the index it
# should be, so the last file stays.
MIN_PACKAGES = 1000


def fetch():
    """Typst Universe's index: every version of every package, as a list of
    {"name", "version", "updatedAt", ...}. Raises when it can't be read."""
    return json.loads(download.get(INDEX))


def version_key(version):
    """Typst's versions are semver (0.10.0 after 0.9.2): their numbers, in
    order; anything else sorts first."""
    try:
        return (1, tuple(int(part) for part in version.split(".")))
    except ValueError:
        return (0, ())


def newest(index):
    """{name: {"version", "released"}}: each package's newest version in
    index, and the day it was published (UTC), when the index says."""
    found = {}
    for entry in index:
        name, version = entry.get("name"), entry.get("version")
        if not name or not version:
            continue
        if name in found and version_key(version) <= version_key(
            found[name]["version"]
        ):
            continue
        found[name] = {"version": version}
        if isinstance(at := entry.get("updatedAt"), int):
            found[name]["released"] = datetime.fromtimestamp(at, UTC).date().isoformat()
    return dict(sorted(found.items()))


def write(directory, packages, now):
    """Write typst.json.gz (packages: newest's) to directory."""
    os.makedirs(directory, exist_ok=True)
    body = {
        "format": FORMAT,
        "fetchedAt": now.isoformat(timespec="seconds"),
        "packages": packages,
    }
    data = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    with open(os.path.join(directory, FILE), "wb") as f:
        f.write(gzip.compress(data, compresslevel=9, mtime=0))


def read(directory):
    """typst.json.gz in directory, or None if there's none."""
    try:
        with gzip.open(os.path.join(directory, FILE), "rt") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def update(directory, now):
    """Bring typst.json.gz up to date: {"at", "packages"} for meta.json, or
    None when the index couldn't be read (the last file stays, with a
    warning: the Repology digest goes on regardless)."""
    print("Reading Typst Universe's index...", file=sys.stderr)
    try:
        packages = newest(fetch())
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"::warning::Typst Universe's index: {e}; kept the last", file=sys.stderr)
        return None
    if len(packages) < MIN_PACKAGES:
        print(
            f"::warning::Only {len(packages):,} Typst packages (expected over "
            f"{MIN_PACKAGES:,}): kept the last",
            file=sys.stderr,
        )
        return None
    write(directory, packages, now)
    return {"at": now.isoformat(timespec="seconds"), "packages": len(packages)}
