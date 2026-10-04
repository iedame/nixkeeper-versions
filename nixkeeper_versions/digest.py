"""The digest nixkeeper reads (data/): projects.json.gz, every Repology
project with a nixpkgs package (nix_unstable), as nixkeeper keeps a
project's data, with when each was last read; and meta.json, about the
sweeps that made it.

projects.json.gz is one JSON object:

    {"projects": {"tracy": [{"repo": "nix_unstable", "srcname": "tracy_0_11",
                             "version": "0.11.1", "status": "legacy"}, ...],
                  ...},
     "checked": {"tracy": "2026-10-04", ...}}

each entry with Repology's "repo", "version", "status", and "srcname" (for
nixpkgs, the attribute: nixkeeper finds a package's project by it) and
"vulnerable": true when they're there, each entry once: as Repology's API
gives them, trimmed as nixkeeper does (its sources/repology.py)."""

import gzip
import json
import os

FORMAT = 1
PROJECTS = "projects.json.gz"
META = "meta.json"
NIX_REPO = "nix_unstable"
FIELDS = ("repo", "srcname", "version", "status", "vulnerable")


def trimmed(entries):
    """entries with only FIELDS, each once, in Repology's order."""
    seen, kept = set(), []
    for entry in entries or []:
        entry = {k: entry[k] for k in FIELDS if k in entry}
        key = json.dumps(entry, sort_keys=True)
        if key not in seen:
            seen.add(key)
            kept.append(entry)
    return kept


def nix_outdated(entries):
    """Whether a nixpkgs package of the project is outdated (so it's on
    Repology's outdated list)."""
    return any(e["repo"] == NIX_REPO and e.get("status") == "outdated" for e in entries)


def has_nix(entries):
    return any(e["repo"] == NIX_REPO for e in entries)


class Digest:
    """The projects (name -> trimmed entries) and when each was last read
    (name -> ISO day)."""

    def __init__(self, projects=None, checked=None):
        self.projects = projects or {}
        self.checked = checked or {}

    def put(self, name, entries, day):
        """Record a project as read today; one that no longer has a nixpkgs
        package is dropped."""
        entries = trimmed(entries)
        if has_nix(entries):
            self.projects[name] = entries
            self.checked[name] = day
        else:
            self.drop(name)

    def drop(self, name):
        self.projects.pop(name, None)
        self.checked.pop(name, None)


def write(directory, found, meta):
    """Write projects.json.gz and meta.json to directory. The same data gives
    the same bytes (sorted, mtime 0)."""
    os.makedirs(directory, exist_ok=True)
    body = {"projects": found.projects, "checked": found.checked}
    data = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    with open(os.path.join(directory, PROJECTS), "wb") as f:
        f.write(gzip.compress(data, compresslevel=9, mtime=0))
    with open(os.path.join(directory, META), "w") as f:
        json.dump({"format": FORMAT, **meta}, f, indent=2, sort_keys=True)
        f.write("\n")


def read(directory):
    """(Digest, meta) in directory, or (an empty Digest, {}) if none yet."""
    try:
        with open(os.path.join(directory, META)) as f:
            meta = json.load(f)
        with gzip.open(os.path.join(directory, PROJECTS), "rt") as f:
            body = json.load(f)
    except FileNotFoundError:
        return Digest(), {}
    return Digest(body["projects"], body["checked"]), meta
