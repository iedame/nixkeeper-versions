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

- [`data/typst.json.gz`](https://raw.githubusercontent.com/iedame/nixkeeper-versions/data/data/typst.json.gz)
  (about 17 KB): the newest version of each package on
  [Typst Universe](https://typst.app/universe/), the source of nixpkgs'
  `typstPackages`, whose versions Repology mostly can't compare, and the
  day it was published:

  ```json
  {"format": 1, "fetchedAt": "2026-10-07T04:10:00+00:00",
   "packages": {"cetz": {"version": "0.5.2", "released": "2026-05-07"}, ...}}
  ```

  From Universe's index, one request a run (2.3 MB, every version of every
  package). A run that can't read it keeps the last (`fetchedAt` says how
  old).

- [`data/emacs.json.gz`](https://raw.githubusercontent.com/iedame/nixkeeper-versions/data/data/emacs.json.gz)
  (about 95 KB): the newest version of each package in each Emacs package
  archive nixpkgs' `emacsPackages` are made from (MELPA, MELPA Stable,
  NonGNU ELPA, GNU ELPA), whose versions Repology mostly can't compare
  (MELPA's are dates):

  ```json
  {"format": 1, "fetchedAt": "2026-10-08T04:10:00+00:00",
   "archives": {"melpa": {"magit": "20251005.508", ...},
                "melpaStable": {"rtags": "3.23", ...},
                "nongnu": {"jabber": "0.15.0", ...}, "gnu": {"auctex": "14.2.0", ...}}}
  ```

  MELPA's versions are the date and time of the commit it built. From the
  archives' indexes, the ones nixpkgs' update scripts read: four requests a
  run (MELPA's two as JSON, the ELPAs' as Emacs Lisp data, of which only
  each entry's name and version are read). A run that can't read all four
  keeps the last (`fetchedAt` says how old).

- [`data/stackage.json.gz`](https://raw.githubusercontent.com/iedame/nixkeeper-versions/data/data/stackage.json.gz)
  (about 25 KB): the Stackage LTS series nixpkgs pins about 3,400 of its
  `haskellPackages` to, and that series' newest version of each: for
  those, the version to be at, not Hackage's newest (Stackage holds newer
  ones back until its next series):

  ```json
  {"format": 1, "fetchedAt": "2026-10-08T04:10:00+00:00",
   "series": "lts-24", "nixpkgs": "lts-24.38", "snapshot": "lts-24.62",
   "versions": {"aeson": "2.2.5.1", ...}}
  ```

  Which series, and which packages, from `stackage.yaml` on nixpkgs master
  (its first line: "# Stackage LTS 24.38"); the versions from that
  series' newest snapshot on stackage.org (its `cabal.config`, as nixpkgs'
  own update script reads it). Two requests a run; a run that can't read
  either keeps the last.

- [`data/releases.json.gz`](https://raw.githubusercontent.com/iedame/nixkeeper-versions/data/data/releases.json.gz):
  for each nixpkgs package fetched from a GitHub tag (about 34,000
  attributes outside the sets above, 21,000 repositories), its newest
  version on GitHub, so nixkeeper doesn't depend on Repology for them:

  ```json
  {"format": 1, "fetchedAt": "...", "evaluatedAt": "...", "revision": "...",
   "packages": {"whisky": {"repo": "Whisky-App/Whisky", "version": "2.3.5",
                           "tag": "2.4.0", "release": "2.4.0", "read": "2026-10-08"}, ...},
   "gone": ["owner/repo", ...]}
  ```

  `version` is nixpkgs'; `tag` the newest of the repository's tags that
  match the package's tag scheme (as nixkeeper's update checks work it out
  from its source: `v2.4.0` for `v2.3.5`), by Repology's version order;
  `release` its latest release's, when that matches (drafts and
  pre-releases left out); `read` when the repository was read. Where each
  package comes from is evaluated from nixpkgs weekly (with Nix and
  nixkeeper's own code, this flake's input: about a minute); each run reads
  a seventh of the repositories, so each weekly, plus those never read and
  those of packages Repology has outdated, 25 a GraphQL query with the
  workflow's own token. `releases-state.json.gz` keeps what that needs
  between runs. A run that can't evaluate or reach GitHub keeps the last.

- [`data/meta.json`](https://raw.githubusercontent.com/iedame/nixkeeper-versions/data/data/meta.json):
  when the outdated projects were last read (`outdatedAt`), how many there
  are, where the weekly rotation is (`rotation.next`, and `rotation.lapAt`,
  when it last went through all of them), how many projects there are, and
  how many requests the run made, and when Typst Universe's index, the
  Emacs archives, Stackage and GitHub were last read and how many packages
  they had (`typst`, `emacs`, `stackage`, `releases`).

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
