"""Stackage LTS, which nixpkgs pins about 3,400 of its haskellPackages to
(pkgs/development/haskell-modules/configuration-hackage2nix/stackage.yaml:
"# Stackage LTS 24.38"): for those, the version to be at is the newest of
that LTS series, not Hackage's newest, which Stackage holds back until a
new series on purpose. Each run reads which series nixpkgs follows, and
the packages it pins, from stackage.yaml on nixpkgs master, then that
series' newest snapshot from stackage.org (its cabal.config, as nixpkgs'
own update script reads it; two requests), written to
data/stackage.json.gz:

    {"format": 1, "fetchedAt": "2026-10-08T04:10:00+00:00",
     "series": "lts-24", "nixpkgs": "lts-24.38", "snapshot": "lts-24.62",
     "versions": {"aeson": "2.2.4.1", ...}}

versions: the snapshot's version of each package nixpkgs pins. A run that
can't read either keeps the last file (its fetchedAt says how old it is)."""

import gzip
import json
import os
import re
import sys
import urllib.error

from . import download

FILE = "stackage.json.gz"
FORMAT = 1
NIXPKGS_PINS = (
    "https://raw.githubusercontent.com/NixOS/nixpkgs/master/pkgs/development/"
    "haskell-modules/configuration-hackage2nix/stackage.yaml"
)
SNAPSHOT = "https://www.stackage.org/{series}/cabal.config"
# stackage.yaml's first line, and each of its pins ("  - aeson ==2.2.4.1").
FOLLOWED = re.compile(r"#\s*Stackage LTS (\d+)\.(\d+)")
PIN = re.compile(r"^\s*-\s*([A-Za-z0-9][\w-]*)\s*==", re.MULTILINE)
# cabal.config: which snapshot it is, and its constraints ("aeson ==2.2.4.1,";
# GHC's own packages say "installed" instead, and aren't pinned).
SNAPSHOT_ID = re.compile(r"stackage\.org/snapshot/(lts-\d+\.\d+)")
CONSTRAINT = re.compile(r"([A-Za-z0-9][\w-]*)\s*==\s*([\d.]+)")
# Fewer pins or packages than this (about 3,400 each on 2026-10-07): not
# the file it should be.
MIN_PACKAGES = 2000


def followed(text):
    """(series, snapshot) nixpkgs follows, from stackage.yaml's text:
    ("lts-24", "lts-24.38"). Raises when it doesn't say."""
    found = FOLLOWED.search(text)
    if not found:
        raise ValueError("stackage.yaml doesn't say which Stackage LTS it follows")
    major, minor = found.groups()
    return f"lts-{major}", f"lts-{major}.{minor}"


def pins(text):
    """The packages stackage.yaml pins, by name."""
    return set(PIN.findall(text))


def snapshot(text):
    """(snapshot id, {package: version}) from a snapshot's cabal.config."""
    found = SNAPSHOT_ID.search(text)
    if not found:
        raise ValueError("the snapshot's cabal.config doesn't say which it is")
    return found.group(1), dict(CONSTRAINT.findall(text))


def read_stackage():
    """{"series", "nixpkgs", "snapshot", "versions"}: what write writes.
    Raises when either file can't be read, or has too few packages."""
    pinned_text = download.get(NIXPKGS_PINS).decode("utf-8", "replace")
    series, nixpkgs = followed(pinned_text)
    pinned = pins(pinned_text)
    snapshot_id, versions = snapshot(
        download.get(SNAPSHOT.format(series=series)).decode("utf-8", "replace")
    )
    if len(pinned) < MIN_PACKAGES or len(versions) < MIN_PACKAGES:
        raise ValueError(
            f"only {len(pinned):,} pins in nixpkgs and {len(versions):,} packages "
            f"in {snapshot_id} (expected over {MIN_PACKAGES:,} each)"
        )
    return {
        "series": series,
        "nixpkgs": nixpkgs,
        "snapshot": snapshot_id,
        "versions": {n: versions[n] for n in sorted(pinned) if n in versions},
    }


def write(directory, found, now):
    os.makedirs(directory, exist_ok=True)
    body = {"format": FORMAT, "fetchedAt": now.isoformat(timespec="seconds"), **found}
    data = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    with open(os.path.join(directory, FILE), "wb") as f:
        f.write(gzip.compress(data, compresslevel=9, mtime=0))


def read(directory):
    """stackage.json.gz in directory, or None if there's none."""
    try:
        with gzip.open(os.path.join(directory, FILE), "rt") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def update(directory, now):
    """Bring stackage.json.gz up to date: {"at", "snapshot", "packages"} for
    meta.json, or None when it couldn't be read (the last file stays, with a
    warning: the Repology digest goes on regardless)."""
    print("Reading Stackage LTS...", file=sys.stderr)
    try:
        found = read_stackage()
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"::warning::Stackage: {e}; kept the last", file=sys.stderr)
        return None
    write(directory, found, now)
    return {
        "at": now.isoformat(timespec="seconds"),
        "snapshot": found["snapshot"],
        "packages": len(found["versions"]),
    }
