"""`python3 -m nixkeeper_versions [DATA_DIR] [--full]`: bring the digest in
DATA_DIR (default data/) up to date with Repology. Each run (daily):

1. reads Repology's list of nixpkgs' outdated projects, all of it, as
   nixpkgs-update does: every outdated package's versions, a day old at
   most;
2. reads again, one by one, the projects that were outdated and no longer
   are (updated in nixpkgs, most of them), up to MAX_SINGLE;
3. reads the next ROTATION_PAGES pages of all nixpkgs' projects, going on
   where the last run stopped, so every project (up-to-date ones' other
   repositories, legacy versions, vulnerabilities) is read once a week.

With no digest yet, or --full, step 3 reads all of them at once (about 600
pages, an hour). Nothing is written when a step fails: the last digest
stays."""

import sys
import time
from datetime import UTC, datetime

from . import digest, repology, sweep

# All of nixpkgs' projects (about 119,000, 600 pages) over about 7 runs.
ROTATION_PAGES = 90
MAX_SINGLE = 400
# Fewer than this many outdated projects (about 13,000), or projects in all,
# means Repology answered wrong: nothing is written.
MIN_OUTDATED = 5_000
MIN_PROJECTS = 100_000


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    full = "--full" in argv
    args = [a for a in argv if a != "--full"]
    directory = args[0] if args else "data"
    now = datetime.now(UTC)
    today = now.date().isoformat()
    started = time.monotonic()
    found, meta = digest.read(directory)
    before = dict(found.projects)

    print("Reading Repology's outdated nixpkgs projects...", file=sys.stderr)
    outdated, _ = sweep.walk(outdated=True)
    if len(outdated) < MIN_OUTDATED:
        print(
            f"::error::Only {len(outdated):,} outdated projects (expected over "
            f"{MIN_OUTDATED:,}): not written.",
            file=sys.stderr,
        )
        return 1
    for name, entries in outdated.items():
        found.put(name, entries, today)

    caught_up = sorted(
        n
        for n, entries in before.items()
        if digest.nix_outdated(entries) and n not in outdated
    )
    asked = caught_up[:MAX_SINGLE]
    print(f"Reading {len(asked):,} projects no longer outdated...", file=sys.stderr)
    for name in asked:
        entries = repology.project(name)
        if entries is None:
            found.drop(name)
        else:
            found.put(name, entries, today)

    rotation = dict(meta.get("rotation") or {})
    whole = full or not before
    start = "" if whole else rotation.get("next", "")
    where = f"{ROTATION_PAGES} pages of nixpkgs projects from {start or 'the start'}"
    print(f"Reading {'all nixpkgs projects' if whole else where}...", file=sys.stderr)
    read, end = sweep.walk(start, max_pages=None if whole else ROTATION_PAGES)
    for name, entries in read.items():
        found.put(name, entries, today)
    # Read their whole range: those it didn't have are no longer nixpkgs'.
    gone = [
        n for n in found.projects if sweep.in_range(n, start, end) and n not in read
    ]
    for name in gone:
        found.drop(name)
    rotation["next"] = end or ""
    if end is None:
        rotation["lapAt"] = now.isoformat(timespec="seconds")
    if len(found.projects) < MIN_PROJECTS and (whole or len(before) >= MIN_PROJECTS):
        print(
            f"::error::Only {len(found.projects):,} projects (expected over "
            f"{MIN_PROJECTS:,}): not written.",
            file=sys.stderr,
        )
        return 1

    digest.write(
        directory,
        found,
        {
            "outdatedAt": now.isoformat(timespec="seconds"),
            "outdated": len(outdated),
            "caughtUp": len(caught_up),
            "caughtUpRead": len(asked),
            "rotation": rotation,
            "projects": len(found.projects),
            "requests": repology.requests_made,
        },
    )
    minutes = (time.monotonic() - started) / 60
    print(
        f"{len(found.projects):,} projects ({len(outdated):,} outdated; "
        f"{len(asked):,} of {len(caught_up):,} no longer outdated read again; "
        f"{len(read):,} read in the rotation, {len(gone):,} gone), "
        f"{repology.requests_made:,} requests, {minutes:.0f} min",
        file=sys.stderr,
    )
    return 0
