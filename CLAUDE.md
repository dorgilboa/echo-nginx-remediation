# Echo assignment - working agreement

Goal: ship a drop-in replacement for `nginx:1.25-bookworm` (1.25.5) with >=2 CVEs fixed
(one dependency version bump, one backport patch), a reproducible build from `debian:bookworm-slim`,
a Containerfile, a compatibility test, VEX for a backported CVE, and a README. Full brief: the PDF
"Software Engineer - Build It, Patch It, Ship It".

The user is new to image vulnerability remediation and wants to LEARN the process.

## At the start of every session / prompt
1. Read `LOG.md` (local, gitignored progress log) and `git log` to see where we are.
2. Say briefly where we are in the roadmap below and what the next step is.
3. Explain the next step in plain language: what it is, why it matters, what the commands do. Guide, don't race ahead.
4. Do only what the user asks; propose the next step rather than silently doing it.

## Roadmap (mark progress in LOG.md)
1. Environment setup (done)
2. Baseline scans: trivy + grype on nginx:1.25-bookworm -> `baseline/`
3. Triage: per CVE - affected binary/lib, upstream fix version, bump / backport / remove; choose which to fix and why
4. Build script + Makefile: fetch pinned nginx tarball (verify checksum) in clean debian:bookworm-slim, apply patches, build .deb
5. Patches: one dependency bump + one backport (`build/patches/CVE-XXXX-XXXXX.patch`)
6. Containerfile: install .deb, match upstream layout/user/workdir/ports/entrypoint
7. Rescan + diff; VEX document for a backported CVE; show it disappear with trivy/grype --vex
8. Compatibility test (Python or Go) + `make test`
9. README: build steps, image size, per-CVE table, residual risk, surprises, AI-tool usage

## Rules
- Logging: after each meaningful action, append a SHORT entry to `LOG.md`. LOG.md is a draft: it is
  gitignored and must NOT be committed or pushed. Only deliver it to the repo when the user says so.
- Git: never add Co-Authored-By or any Claude/AI attribution to commits or files. The user is the sole author.
- Do not commit nginx source or tarballs; the build fetches them.
- Ask before outward-facing actions (push, creating repos, force-push).
