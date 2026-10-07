"""Downloading a source's whole index in one request (Typst Universe's,
the Emacs archives'), as politely as Repology is asked: gzipped, with a
User-Agent linking this repository, and given up when the answer takes
too long to arrive."""

import gzip
import time
import urllib.request

from . import repology


def get(url):
    """The body at url, as bytes. Raises when it can't be read."""
    req = urllib.request.Request(
        url, headers={"User-Agent": repology.USER_AGENT, "Accept-Encoding": "gzip"}
    )
    deadline = time.monotonic() + repology.DEADLINE
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = repology._read(resp, deadline)
        if resp.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    return body
