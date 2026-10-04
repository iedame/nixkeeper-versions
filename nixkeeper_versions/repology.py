"""Asking Repology's API (https://repology.org/api), as its rules ask: at most
one request a second, gzipped, with a User-Agent linking this repository
(and so its issue tracker). Only nixpkgs' projects (inrepo=nix_unstable):
200 to a page, in name order, from a given name on (inclusive); or one
project by name."""

import gzip
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://repology.org/api/v1"
NIX_REPO = "nix_unstable"
USER_AGENT = "nixkeeper-versions (+https://github.com/iedame/nixkeeper-versions)"
# Seconds from one request's start to the next's: Repology allows one a
# second; a little more, to be sure.
PAUSE = 1.1
# Retries of a failed request, and how long to wait before each (or as long
# as Repology says with Retry-After, up to MAX_RETRY_AFTER).
RETRY_DELAYS = (10, 60)
MAX_RETRY_AFTER = 300

_last = 0.0
requests_made = 0


def _wait():
    global _last
    pause = _last + PAUSE - time.monotonic()
    if pause > 0:
        time.sleep(pause)
    _last = time.monotonic()


def get(path):
    """The JSON at path under the API, or None on 404. A failed request is
    retried after RETRY_DELAYS (longer if Repology asks, with Retry-After,
    up to MAX_RETRY_AFTER); raises once every attempt failed."""
    global requests_made
    for attempt in range(len(RETRY_DELAYS) + 1):
        _wait()
        requests_made += 1
        req = urllib.request.Request(
            API + path, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
        )
        asked = 0
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return json.loads(body)
        except urllib.error.HTTPError as e:
            e.close()
            if e.code == 404:
                return None
            retry_after = e.headers.get("Retry-After") or ""
            if retry_after.isdigit() and int(retry_after) <= MAX_RETRY_AFTER:
                asked = int(retry_after)
            error = e
        except (urllib.error.URLError, OSError, ValueError) as e:
            error = e
        print(f"  Repology ({path}): {error}", file=sys.stderr)
        if attempt < len(RETRY_DELAYS):
            delay = max(RETRY_DELAYS[attempt], asked)
            print(f"  retrying in {delay}s...", file=sys.stderr)
            time.sleep(delay)
    raise error


def page(start, outdated=False):
    """{project: entries} for up to 200 of nixpkgs' projects named start or
    later (all of them from the first when start is ""); outdated: only
    those whose nixpkgs package is outdated."""
    query = {"inrepo": NIX_REPO}
    if outdated:
        query["outdated"] = "1"
    name = urllib.parse.quote(start, safe="") + "/" if start else ""
    return get(f"/projects/{name}?{urllib.parse.urlencode(query)}") or {}


def project(name):
    """A project's entries, or None if Repology has no such project."""
    return get(f"/project/{urllib.parse.quote(name, safe='')}")
