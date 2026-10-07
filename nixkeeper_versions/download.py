"""Downloading a source's whole index in one request (Typst Universe's,
the Emacs archives'), as politely as Repology is asked: gzipped, with a
User-Agent linking this repository, and given up when the answer takes
too long to arrive."""

import gzip
import time
import urllib.request

from . import repology


def get(url, first_bytes=None):
    """The body at url, as bytes; with first_bytes, only that many from its
    start (a Range request, for a line at the top of a big file). Raises
    when it can't be read."""
    headers = {"User-Agent": repology.USER_AGENT}
    if first_bytes:
        headers["Range"] = f"bytes=0-{first_bytes - 1}"
    else:
        headers["Accept-Encoding"] = "gzip"
    req = urllib.request.Request(url, headers=headers)
    deadline = time.monotonic() + repology.DEADLINE
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = repology._read(resp, deadline)
        if resp.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    return body
