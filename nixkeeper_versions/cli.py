"""`python3 -m nixkeeper_versions [DATA_DIR] [--full] [--if-older HOURS]
[--sources-only]`:
bring the digest in
DATA_DIR (default data/) up to date with Repology, and beside it the
newest versions of Typst Universe (typst.py) and the Emacs package
archives (emacs.py), the Stackage LTS nixpkgs follows (stackage.py), CRAN
and the Bioconductor release nixpkgs pins (cran.py), and GitHub-hosted
packages' newest releases and tags (releases.py: weekly where they come
from, daily a seventh of their repositories), and nixpkgs' own facts for
readers without Nix (packages.py: every attribute's pname and version,
and the sources releases.py evaluated): a failed read of those keeps
their last, without stopping the digest. Each run (daily):

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
stays. --if-older HOURS: only when the last run is older than that (or
there's none), for a run started twice (by the schedule and by hand or a
scheduler outside GitHub) to sweep once. --sources-only: the other sources
only, Repology left alone (no request to it; projects.jsonl.gz as it was),
for trying them without spending Repology's daily allowance."""

import json
import os
import sys
import time
from datetime import UTC, datetime

from . import cran, digest, emacs, packages, releases, repology, stackage, sweep, typst

# All of nixpkgs' projects (about 119,000, 600 pages) over about 7 runs.
ROTATION_PAGES = 90
MAX_SINGLE = 400
# Fewer than this many outdated projects (about 13,000), or projects in all,
# means Repology answered wrong: nothing is written.
MIN_OUTDATED = 5_000
MIN_PROJECTS = 100_000


def last_run_age(directory, now):
    """Hours since the last run that wrote the digest, or None if none."""
    try:
        with open(os.path.join(directory, digest.META)) as f:
            at = json.load(f).get("outdatedAt")
    except (FileNotFoundError, ValueError):
        return None
    return (now - datetime.fromisoformat(at)).total_seconds() / 3600 if at else None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if_older = None
    if "--if-older" in argv:
        i = argv.index("--if-older")
        if_older = float(argv[i + 1])
        del argv[i : i + 2]
    full = "--full" in argv
    sources_only = "--sources-only" in argv
    args = [a for a in argv if a not in ("--full", "--sources-only")]
    directory = args[0] if args else "data"
    now = datetime.now(UTC)
    if if_older is not None:
        age = last_run_age(directory, now)
        if age is not None and age < if_older:
            print(
                f"The last run was {age:.1f} hours ago (under {if_older:g}): "
                "nothing to do.",
                file=sys.stderr,
            )
            return 0
    today = now.date().isoformat()
    started = time.monotonic()
    found, meta = digest.read(directory)
    # Their own files: a failed read keeps the last, and the digest goes on.
    typst_read = typst.update(directory, now) or meta.get("typst")
    emacs_read = emacs.update(directory, now) or meta.get("emacs")
    stackage_read = stackage.update(directory, now) or meta.get("stackage")
    cran_read = cran.update(directory, now) or meta.get("cran")
    # The packages the last digest has outdated: their repositories are read
    # daily (whatever Repology does today).
    outdated_before = {
        e["srcname"]
        for entries in found.projects.values()
        for e in entries
        if e["repo"] == digest.NIX_REPO
        and e.get("status") == "outdated"
        and e.get("srcname")
    }
    evaluated = []
    releases_read = releases.update(
        directory, now, outdated_before, lambda *found: evaluated.append(found)
    ) or meta.get("releases")
    # nixpkgs' facts for readers without Nix: the index daily, the sources
    # releases.py evaluated (weekly).
    nixpkgs_read = packages.update(
        directory, now, evaluated[0] if evaluated else None
    ) or meta.get("nixpkgs")
    if sources_only:
        read_now = {
            "typst": typst_read,
            "emacs": emacs_read,
            "stackage": stackage_read,
            "cran": cran_read,
            "releases": releases_read,
            "nixpkgs": nixpkgs_read,
        }
        meta = {k: v for k, v in meta.items() if k != "format"}
        digest.write_meta(directory, meta | {k: v for k, v in read_now.items() if v})
        print("The other sources only: Repology left alone.", file=sys.stderr)
        return 0
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
            **({"typst": typst_read} if typst_read else {}),
            **({"emacs": emacs_read} if emacs_read else {}),
            **({"stackage": stackage_read} if stackage_read else {}),
            **({"cran": cran_read} if cran_read else {}),
            **({"releases": releases_read} if releases_read else {}),
            **({"nixpkgs": nixpkgs_read} if nixpkgs_read else {}),
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
