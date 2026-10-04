"""Walking Repology's lists of nixpkgs' projects, a page (200 projects) at a
time, in name order: each page starts at the last name of the one before
(Repology's start is inclusive), until a page comes back short."""

import sys

from . import repology

PAGE_SIZE = 200


def walk(start="", outdated=False, max_pages=None):
    """({project: entries} read, where to go on from: the last name read, or
    None once the list's end was reached), reading at most max_pages pages
    from start ("" for the first)."""
    found, cursor, pages = {}, start, 0
    while max_pages is None or pages < max_pages:
        got = repology.page(cursor, outdated)
        pages += 1
        if cursor and got and cursor not in got and min(got) < cursor:
            # Repology's name order isn't this one: pages could be missed.
            print(
                f"::warning::Repology's page from {cursor} starts at {min(got)}",
                file=sys.stderr,
            )
        found.update(got)
        if len(got) < PAGE_SIZE:
            return found, None
        cursor = max(got)
    return found, cursor


def in_range(name, start, end):
    """Whether name is in [start, end] (end None: to the list's end)."""
    return name >= start and (end is None or name <= end)
