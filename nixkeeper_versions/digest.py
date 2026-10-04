"""The digest nixkeeper reads (data/): projects.jsonl.gz, every Repology
project with a nixpkgs package (nix_unstable), as nixkeeper keeps a
project's data, with when each was last read; and meta.json, about the
sweeps that made it.

projects.jsonl.gz has one project per line, sorted by name:

    {"project": "tracy", "checked": "2026-10-04",
     "entries": [{"repo": "nix_unstable", "srcname": "tracy_0_11",
                  "version": "0.11.1", "status": "legacy"}, ...]}

so a reader can go through it line by line and keep only the projects it
wants (nixkeeper: those of the packages it tracks), instead of holding all
of them (about 1.4 GB of memory, as one JSON object). Each entry has
Repology's "repo", "version", "status", and "srcname" (for nixpkgs, the
attribute: nixkeeper finds a package's project by it) and "vulnerable":
true when they're there, each entry once: as Repology's API gives them,
trimmed as nixkeeper does (its sources/repology.py)."""

import gzip
import json
import os

FORMAT = 1
PROJECTS = "projects.jsonl.gz"
# The first digest's file, one JSON object: read once, then replaced.
OLD_PROJECTS = "projects.json.gz"
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
    """Write projects.jsonl.gz and meta.json to directory (and remove the old
    projects.json.gz). The same data gives the same bytes (sorted, mtime 0)."""
    os.makedirs(directory, exist_ok=True)
    old = os.path.join(directory, OLD_PROJECTS)
    if os.path.exists(old):
        os.remove(old)
    lines = (
        json.dumps(
            {
                "project": name,
                "checked": found.checked[name],
                "entries": found.projects[name],
            },
            separators=(",", ":"),
        )
        + "\n"
        for name in sorted(found.projects)
    )
    data = "".join(lines).encode()
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
        found = Digest()
        path = os.path.join(directory, PROJECTS)
        if not os.path.exists(path) and os.path.exists(
            old := os.path.join(directory, OLD_PROJECTS)
        ):
            with gzip.open(old, "rt") as f:
                body = json.load(f)
            return Digest(body["projects"], body["checked"]), meta
        with gzip.open(path, "rt") as f:
            for line in f:
                project = json.loads(line)
                found.projects[project["project"]] = project["entries"]
                found.checked[project["project"]] = project["checked"]
    except FileNotFoundError:
        return Digest(), {}
    return found, meta
