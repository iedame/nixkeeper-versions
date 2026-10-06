import gzip
import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from nixkeeper_versions import cli, digest, repology, sweep


def nix(attr, version, status, **extra):
    return {
        "repo": "nix_unstable",
        "srcname": attr,
        "version": version,
        "status": status,
        **extra,
    }


def other(repo, version, status="newest"):
    return {"repo": repo, "srcname": "x", "version": version, "status": status}


class FakeRepology:
    """Repology's API over projects ({name: entries}): pages of PAGE_SIZE in
    name order from an inclusive start, outdated ones only when asked."""

    def __init__(self, projects):
        self.projects = projects
        self.asked = []

    def page(self, start, outdated=False):
        self.asked.append(("page", start, outdated))
        names = sorted(
            n
            for n, entries in self.projects.items()
            if n >= start and (not outdated or digest.nix_outdated(entries))
        )
        return {n: self.projects[n] for n in names[: sweep.PAGE_SIZE]}

    def project(self, name):
        self.asked.append(("project", name))
        return self.projects.get(name)


class Walk(unittest.TestCase):
    def test_pages_from_inclusive_starts(self):
        names = [f"p{i:03}" for i in range(450)]
        fake = FakeRepology({n: [nix(n, "1", "newest")] for n in names})
        with mock.patch.object(repology, "page", side_effect=fake.page):
            found, end = sweep.walk()
            self.assertEqual((sorted(found), end), (names, None))
            found, end = sweep.walk("", max_pages=2)
        # Each page starts at the last name of the one before.
        self.assertEqual(end, names[398])
        self.assertEqual(len(found), 399)
        self.assertEqual(fake.asked[-1], ("page", names[199], False))


class Digest(unittest.TestCase):
    def test_trimmed_once_each(self):
        entries = [
            {**nix("xournalpp", "1.3.7", "outdated"), "summary": "notes"},
            {**other("arch", "1.3.8"), "binname": "xournalpp"},
            {**other("arch", "1.3.8"), "binname": "xournalpp-doc"},
        ]
        self.assertEqual(
            digest.trimmed(entries),
            [nix("xournalpp", "1.3.7", "outdated"), other("arch", "1.3.8")],
        )

    def test_put_drops_a_project_without_nixpkgs(self):
        found = digest.Digest({"a": [nix("a", "1", "newest")]}, {"a": "2026-10-01"})
        found.put("a", [other("arch", "2")], "2026-10-04")
        self.assertEqual((found.projects, found.checked), ({}, {}))

    def test_write_read(self):
        found = digest.Digest()
        found.put("a", [nix("a", "1", "outdated", vulnerable=True)], "2026-10-04")
        with tempfile.TemporaryDirectory() as d:
            digest.write(d, found, {"projects": 1})
            again, meta = digest.read(d)
            none, none_meta = digest.read(d + "/none")
        self.assertEqual((none.projects, none.checked, none_meta), ({}, {}, {}))
        self.assertEqual(again.projects, found.projects)
        self.assertEqual(again.checked, {"a": "2026-10-04"})
        self.assertEqual(meta, {"format": digest.FORMAT, "projects": 1})

    def test_the_first_digests_file_is_read_then_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            with open(f"{d}/meta.json", "w") as f:
                json.dump({"format": 1}, f)
            body = {
                "projects": {"a": [nix("a", "1", "newest")]},
                "checked": {"a": "2026-10-04"},
            }
            with gzip.open(f"{d}/projects.json.gz", "wt") as f:
                json.dump(body, f)
            found, _ = digest.read(d)
            self.assertEqual(found.projects, body["projects"])
            digest.write(d, found, {})
            self.assertEqual(sorted(os.listdir(d)), ["meta.json", "projects.jsonl.gz"])
            self.assertEqual(digest.read(d)[0].checked, {"a": "2026-10-04"})


class Main(unittest.TestCase):
    def run_main(self, d, projects, *args):
        fake = FakeRepology(projects)
        with (
            mock.patch.object(repology, "page", side_effect=fake.page),
            mock.patch.object(repology, "project", side_effect=fake.project),
            mock.patch.object(cli, "MIN_OUTDATED", 1),
            mock.patch.object(cli, "MIN_PROJECTS", 1),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            code = cli.main([d, *args])
        found, meta = digest.read(d)
        return code, found, meta, fake.asked

    def test_two_days(self):
        day1 = {
            "a": [nix("a", "1", "newest"), other("arch", "1")],
            "b": [nix("b", "1", "outdated"), other("arch", "2")],
            "c": [nix("c", "1", "legacy"), nix("c2", "2", "newest")],
        }
        with tempfile.TemporaryDirectory() as d:
            code, found, meta, asked = self.run_main(d, day1)
            self.assertEqual(code, 0)
            self.assertEqual(sorted(found.projects), ["a", "b", "c"])
            self.assertEqual(meta["outdated"], 1)
            self.assertEqual(meta["rotation"]["next"], "")  # a whole lap
            self.assertIn("lapAt", meta["rotation"])

            # b was updated in nixpkgs, c left it, d is new and outdated.
            day2 = {
                "a": day1["a"],
                "b": [nix("b", "2", "newest"), other("arch", "2")],
                "d": [nix("d", "1", "outdated"), other("arch", "3")],
            }
            code, found, meta, asked = self.run_main(d, day2)
        self.assertEqual(code, 0)
        self.assertIn(("project", "b"), asked)  # no longer outdated: read again
        self.assertEqual(found.projects["b"][0]["status"], "newest")
        self.assertEqual(sorted(found.projects), ["a", "b", "d"])  # c is gone
        self.assertEqual((meta["caughtUp"], meta["caughtUpRead"]), (1, 1))

    def test_too_few_outdated_writes_nothing(self):
        with (
            tempfile.TemporaryDirectory() as d,
            mock.patch.object(cli, "MIN_OUTDATED", 5),
        ):
            fake = FakeRepology({"b": [nix("b", "1", "outdated")]})
            with (
                mock.patch.object(repology, "page", side_effect=fake.page),
                mock.patch("sys.stderr", io.StringIO()),
            ):
                self.assertEqual(cli.main([d]), 1)
            self.assertEqual(digest.read(d)[1], {})


class Get(unittest.TestCase):
    def response(self, body):
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = json.dumps(body).encode()
        resp.__enter__.return_value.headers = {}
        return resp

    def error(self, code, retry_after=None):
        headers = {"Retry-After": retry_after} if retry_after else {}
        return urllib.error.HTTPError("u", code, "x", headers, io.BytesIO())

    def test_retries_as_asked_and_404(self):
        sleeps = []
        with (
            mock.patch(
                "urllib.request.urlopen",
                side_effect=[
                    self.error(429, "30"),
                    self.response({"a": []}),
                    self.error(404),
                ],
            ),
            mock.patch("time.sleep", side_effect=sleeps.append),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            self.assertEqual(repology.get("/x"), {"a": []})
            self.assertIsNone(repology.get("/y"))
        self.assertIn(30, sleeps)  # Repology's Retry-After, over the 10 s planned

    def test_user_agent_and_gzip(self):
        with mock.patch(
            "urllib.request.urlopen", return_value=self.response({})
        ) as urlopen:
            repology.page("tracy", outdated=True)
        req = urlopen.call_args.args[0]
        self.assertEqual(
            req.full_url,
            "https://repology.org/api/v1/projects/tracy/?inrepo=nix_unstable&outdated=1",
        )
        self.assertIn(
            "github.com/iedame/nixkeeper-versions", req.get_header("User-agent")
        )
        self.assertEqual(req.get_header("Accept-encoding"), "gzip")


class Deadline(unittest.TestCase):
    """A whole answer has DEADLINE to arrive, however steadily it trickles
    in: a real server on this machine sending a byte at a time."""

    BODY = json.dumps({"x": "y" * 50}).encode()

    def setUp(self):
        body = self.BODY

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    for i in range(len(body)):
                        self.wfile.write(body[i : i + 1])
                        self.wfile.flush()
                        if self.path.startswith("/slow"):
                            time.sleep(0.02)
                except OSError:
                    pass  # the client gave up

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        for patcher in (
            mock.patch.object(
                repology, "API", f"http://127.0.0.1:{server.server_address[1]}"
            ),
            mock.patch.object(repology, "RETRY_DELAYS", ()),
            mock.patch.object(repology, "DEADLINE", 0.3),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_trickle_is_given_up(self):
        # 61 bytes at 20 ms each: 1.2 s, against 0.3 s.
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            repology.get("/slow")
        self.assertLess(time.monotonic() - started, 1)

    def test_a_steady_answer_arrives(self):
        self.assertEqual(repology.get("/fast"), json.loads(self.BODY))
