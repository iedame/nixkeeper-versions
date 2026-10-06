# nixkeeper-versions

A digest of [Repology](https://repology.org)'s data for every nixpkgs
project, for [nixkeeper](https://github.com/iedame/nixkeeper): each
project's versions in every repository Repology knows, kept up to date daily
by a workflow, so nixkeeper reads one file instead of asking Repology about
each of its packages.

It reads Repology the way nixpkgs-update does, from its lists of nixpkgs'
projects, 200 to a request, and less often for what changes less often. All
of nixpkgs costs about 200 requests a day, whatever nixkeeper tracks, well
within Repology's [API rules](https://repology.org/api): at most one request
a second, under 1,000 a day, with a User-Agent linking here.

## The digest

On the `data` branch:

- [`data/projects.jsonl.gz`](https://raw.githubusercontent.com/iedame/nixkeeper-versions/data/data/projects.jsonl.gz)
  (about 12 MB): every Repology project with a nixpkgs package
  (`nix_unstable`), one per line, sorted by name:

  ```json
  {"project": "tracy", "checked": "2026-10-04",
   "entries": [{"repo": "nix_unstable", "srcname": "tracy_0_11",
                "version": "0.11.1", "status": "legacy"}, ...]}
  ```

  with each package of it in every repository, as Repology's API gives
  them, trimmed to `repo`, `version`, `status`, `srcname` (for nixpkgs, the
  package's attribute) and `vulnerable` (when `true`), each entry once; and
  the day it was last read (`checked`). One project per line, so a reader
  can keep only those it wants while reading: about 25 MB of memory instead
  of 1.4 GB for all of them at once.

- [`data/meta.json`](https://raw.githubusercontent.com/iedame/nixkeeper-versions/data/data/meta.json):
  when the outdated projects were last read (`outdatedAt`), how many there
  are, where the weekly rotation is (`rotation.next`, and `rotation.lapAt`,
  when it last went through all of them), how many projects there are, and
  how many requests the run made.

The `data` branch is `main` plus one commit with the digest: each run replaces
it, so no history piles up.

## How it's kept up to date

The "Digest" workflow runs daily at 04:07 UTC, before nixkeeper's daily
sync:

1. **Outdated projects, every day**: Repology's list of nixpkgs' outdated
   projects, all of it (about 70 requests), as nixpkgs-update reads it. Every
   outdated package's versions are at most a day old.
2. **No longer outdated, every day**: the projects that were outdated and
   aren't on today's list (updated in nixpkgs, mostly), read one by one (up
   to 400).
3. **All projects, every week**: a seventh of all nixpkgs' projects (90
   pages), going on where the last run stopped: up-to-date projects' other
   repositories, legacy versions (not on the outdated list), and
   vulnerabilities on versions that aren't outdated (Repology has no list
   of those) are at most a week old. A project that's no longer there is
   dropped.

The first run, with no digest yet, reads all projects at once (about 600
requests, an hour); so does starting the workflow by hand with "full". A
run that fails, or gets far fewer projects than nixpkgs has, publishes
nothing: the last digest stays, and nixkeeper asks Repology itself for what
it lacks.

## Running it

```bash
nix run . -- data
```

brings the digest in `data/` up to date (`-- data --full` reads all
projects; `--if-older 12` only when the last run is over 12 hours old, so a
run started twice sweeps once). `nix flake check` runs the tests and lint, `nix fmt` formats.

## License

MIT
