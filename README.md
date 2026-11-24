# Echo - Build It, Patch It, Ship It

A drop-in replacement for `nginx:1.25-bookworm` (nginx 1.25.5), compiled from source on `debian:bookworm-slim`, with two CVE fixes done end to end and a compatibility test that compares it against the original.

> **Status:** build, image, compatibility test (including file-layout parity), baseline, rescan and VEX are done. What is left is listed under [Open items](#open-items).

## In one minute

| | Original | Ours |
|---|---|---|
| Image | `nginx:1.25-bookworm` | `echo-nginx:test` |
| Size | 273.1 MB | 130.3 MB |
| nginx | 1.25.5 (nginx.org package) | 1.25.5 compiled from the nginx.org tarball |
| libssl3 (OpenSSL) | 3.0.11-1~deb12u2 | 3.0.22-1~deb12u2 |
| CVE-2024-7347 (mp4 module) | present | patched in source |
| Compatibility test | - | 25 of 25 pass |
| nginx CVEs flagged by Grype (CPE mode) | 31 | 31; our VEX file removes 3 of them for Grype (CVE-2024-7347, CVE-2013-0337, CVE-2009-4487) |

Two fixes, two different techniques:
- **Version bump:** OpenSSL (`libssl3`), the TLS library nginx links. One bump clears 10 HIGH/CRITICAL findings.
- **Backport:** CVE-2024-7347 in nginx's mp4 module. The fix exists upstream (1.27.1) but not for 1.25.5, so I applied nginx's official patch to the 1.25.5 source.

## How to build and test

Needs Docker with BuildKit, `make`, and Python 3. Run from the repo root.

```bash
make deb        # clean debian:bookworm-slim -> download + verify source -> patch -> compile -> dist/nginx_1.25.5-1~bookworm_amd64.deb
make image      # installs the .deb into a minimal Debian image: echo-nginx:test
make self-test  # sanity check of the test itself: upstream compared with upstream (must pass)
make test       # upstream vs our image; exits non-zero on any mismatch
make vex        # regenerate the VEX document for the built image (bound to its digest)
```

What `make deb` does (all inside `build/Dockerfile`, nothing pre-baked):

1. `install-deps.sh`: installs compilers and `-dev` libraries; refuses to continue if `libssl-dev` is older than 3.0.22-1~deb12u2.
2. `get-sources.sh`: downloads the 1.25.5 tarball from nginx.org only, checks the PGP signer against a pinned fingerprint, checks the SHA-256, then unpacks. Any mismatch stops the build and leaves nothing behind.
3. `apply-patches.sh`: applies every `build/patches/CVE-*.patch` with no fuzz; fails if one does not apply cleanly.
4. `build-deb.sh`: runs `./configure` with upstream's exact 42 flags (hardening included), `make install` into a staging folder, then `dpkg-deb`.

The `Containerfile` then creates the `nginx` user (uid/gid 101, as upstream) *before* installing the `.deb`, installs it, and copies upstream's entrypoint scripts, log symlinks, port, stop signal and CMD.

## Triage: how the CVEs were chosen

I scanned the original with Trivy and Grype first (`baseline/`): 960 and 890 findings. Most are in base-image libraries that nginx never uses, so I narrowed down to what matters for nginx:

1. **What does nginx actually load?** An SBOM only lists what is installed, so I used `ldd` on the binary: libc6, libcrypt1, zlib1g, libpcre2-8-0 and libssl3. `libssl3` had the most severe findings that have a fix.
2. **Only fixable, only HIGH/CRITICAL.** A bump or backport needs a target version, so unfixed findings were set aside (`scripts/filter-baseline.sh` produces the filtered view).
3. **Check the severity.** Scanners score the library in the worst case. OpenSSL's own advisories rate most of the ten as Low and none sit on nginx's normal TLS handshake path. Severity is not the same as being exploitable in our deployment, and I wrote the README with that in mind.
4. **Confirm the fix target** on the Debian security tracker (Debian version numbers differ from OpenSSL's own numbering): 3.0.22-1~deb12u2 fixes all ten.

## Per-CVE table

Severity is shown as *scanner / vendor's own rating* where they differ.

| CVE | Where | Severity | Method | Evidence |
|---|---|---|---|---|
| CVE-2025-15467 | libssl3 (CMS parsing, not TLS) | High / OpenSSL: High | **bump** to 3.0.22-1~deb12u2 | [rescan/diff.md](rescan/diff.md) (gone after the bump) |
| CVE-2026-84782 | libssl3 (DTLS) | High / High for DTLS users, but nginx has no DTLS | **bump** | [rescan/diff.md](rescan/diff.md); `nm -D` on nginx: 0 DTLS symbols imported (LOG.md, 2026-11-24) |
| CVE-2026-31789 | libssl3 | Critical / OpenSSL: Low (32-bit only, certificates over about 1 GB) | **bump** | [rescan/diff.md](rescan/diff.md) |
| 7 more libssl3 CVEs | libssl3 | High (some Low or Moderate per OpenSSL) | **bump** (same package, same bump) | [rescan/diff.md](rescan/diff.md) table |
| CVE-2024-7347 | nginx `ngx_http_mp4_module.c` | Medium (Grype) / nginx: low | **backport** of nginx's official patch | [patch](build/patches/CVE-2024-7347.patch), [provenance](build/patches/README.md), [test](test/compat_test.py) (`Mp4PatchVerification`), [VEX](vex/echo-nginx.openvex.json), [VEX verification](vex/verification.md) |
| curl, libheif, libtiff, libxml2, krb5 libs, expat... (hundreds) | packages the original ships | various | **remove** (not installed in ours) | [rescan/diff.md](rescan/diff.md). Does **not** count toward the two required fixes |

Of the 694 Trivy findings that disappeared, 496 are only gone because the packages are no longer in the image, and 198 because package versions changed (including a newer Debian base, 12.15 instead of 12.5). Credit for the two real fixes is a small part of that number, and I do not claim otherwise.

## VEX: telling the scanner the fixes are real

A backport changes the code but not the version string (`1.25.5-1~bookworm`), and scanners match on name and version. So after the patch, Grype keeps reporting CVE-2024-7347. A VEX (Vulnerability Exploitability eXchange) file is a small statement shipped next to the image saying "this CVE is `fixed` (or `not_affected`) in this product, and why".

[`vex/echo-nginx.openvex.json`](vex/echo-nginx.openvex.json) is an OpenVEX document with four statements:

| CVE | Status | Why |
|---|---|---|
| CVE-2024-7347 | `fixed` | the backport described above |
| CVE-2026-84782 | `fixed` | Debian's tracker lists the fix in `libssl3` 3.0.22-1~deb12u2, which is installed; some scanners compare with upstream OpenSSL numbering (fixed in 3.0.23) and still match. It is also DTLS code, and nginx imports no DTLS symbols |
| CVE-2013-0337 | `not_affected`, inline mitigation | describes world-readable `access.log`/`error.log`; in this image both are symlinks to `/dev/stdout` and `/dev/stderr` |
| CVE-2009-4487 | `not_affected`, inline mitigation | terminal escape sequences reaching the log; tested: an ESC byte in the User-Agent and request line is logged as the text `` |

**The document is generated, not hand-written** (`make vex`, `vex/make_vex.py`). Because our package keeps upstream's version string, a statement naming only the package would also describe upstream's still-vulnerable package and wrongly hide its findings (tested: it does). So every statement is bound to our image's digest, with the packages as sub-components. A rebuilt image has a new digest, so the file must be regenerated after each rebuild.

**Verification** ([vex/verification.md](vex/verification.md), `vex/verify.py`): each CVE was scanned with and without the VEX file, on our image and on upstream. In Grype all four disappear from our image and **stay flagged on upstream**, which is the check that the VEX does not hide anything it should not.

Limits worth knowing:
- **Trivy can show only part of it.** `trivy --vex` removes the findings Trivy reports: CVE-2013-0337 and CVE-2009-4487 on our image. It never reports CVE-2024-7347 because it has no CPE matching (see difficulty 2), so that one can only be shown with Grype.
- **A VEX is a claim, not proof.** It is only as good as the evidence behind it. The two `not_affected` statements rest on a configuration fact and one logging test.
- **Not covered:** CVE-2026-107494 (QUIC, likely not applicable). I left it out because it is still unconfirmed in the OpenSSL 3.0 source.

## The compatibility test

`test/compat_test.py` (Python, standard library only) starts the original and our image as separate containers, sends both the same requests, and exits non-zero on any difference.

**"Working correctly" means:** for the same request, our image returns the same status, the same headers (all of them, except `Date`, `ETag` and `Last-Modified`, which are only sanity-checked), and the same body as the original. The 25 tests cover:

- default page and 404, custom config, large request body, malformed request
- TLS 1.2 and 1.3 and ALPN
- mp4 serving: whole file, `?start=1`, `?start=1.5`
- file layout parity: every nginx-related file has the same type, mode, owner and link target as upstream, except an explicit list of documented deviations. A second test keeps that list honest (each exception must match something upstream has and nothing we ship)
- image metadata (user, working dir, ports, entrypoint, CMD, env), `nginx -V` configure flags, hashes of the config and entrypoint files
- **fix checks (ours only):** `libssl3` is at least 3.0.22-1~deb12u2 and linked by nginx; the patched mp4 code path logs `unordered mp4 stsc chunks`; the worker survives and still answers

`make self-test` runs the suite with upstream on both sides to prove the test itself is sound. I also ran the fix checks against an unpatched copy: exactly the two fix tests fail and parity still passes, so they can detect a missing fix.

## Difficulties and how I got through them

**1. Choosing what to fix, and what to dig into.**
The scans list ~900 findings. I filtered by what nginx links, whether a fix exists, and severity, then checked each candidate against OpenSSL's advisories and the Debian tracker. That showed scanner severities are often much higher than the vendor's, so I picked CVEs I could actually explain: one that is not TLS code (CMS) and one that is DTLS (nginx does not use it), both inside one bump.

**2. The scanners did not find any nginx CVEs.**
Trivy reported nothing for the nginx package, and Grype only two ancient ones. The reason: both match nginx.org builds against *Debian's* tracker, and Debian ships a different nginx. If I had followed the shortcut (use Debian's package, or `apt`), the original would have looked already patched and there would have been nothing to backport. Instead:
- Grype has a CPE mode (`GRYPE_MATCH_DPKG_USING_CPES=true`) that matches the product name/version, and it flagged 29 nginx CVEs. I use it for the baseline, the rescan and the VEX demo (`baseline/baseline-grype-cpe.*`).
- Trivy has no equivalent (I tested `--detection-priority comprehensive`: still nothing).
- Even CPE mode missed 9 of the 38 CVEs that nginx.org lists for 1.25.5, so nginx's own advisory page is the reference for nginx CVEs, and the scanner output is only a view of it.

**3. Finding a backport I could verify.**
Most nginx advisories link only a mailing-list post. CVE-2024-7347 has an official signed patch file, which I verified (signature, then a dry run on 1.25.5, then compiled with `-Werror`). Trade-off I accepted: a clean patch, but a low-impact bug.

**4. Building a malformed mp4 to test the backport.**
No public exploit file, and writing one from scratch was not realistic. Plan: make a valid small mp4 (48x48 random-noise H.264 made with ffmpeg, command in `test/mp4_tools.py`), then rewrite its `stsc` table in Python so the entries are out of order. I tested this on the original first: it returns HTTP 500 with the message `start time is out mp4 stco chunks` and does **not** crash. So the observable difference to assert is the new log line from the patched check, and that is what the test uses. I did not reproduce the crash, and the README says so.

**5. Writing the compatibility test before the image existed (test first).**
I built the test harness and empty Dockerfile skeletons before any fix, then confirmed three things: upstream vs upstream passes, the skeleton image fails for the right reason (nginx not even running), and an unpatched copy fails exactly the fix tests. A test that cannot fail proves nothing, so each failure was checked. Parity tests (must match the original) are kept apart from fix tests (ours only), because a fixed build is supposed to behave differently on the patched path.

**6. Patch fuzz hid a broken patch.**
My own negative test (corrupting one context line) showed `patch` still applied it with default fuzz. Fixed with `-F0`, so a drifted patch fails the build instead of silently half-applying.

**7. Scanner results that need explaining, not fixing.**
- Our package is flagged by Trivy with 2 "new" ancient LOW CVEs (CVE-2009-4487, CVE-2013-0337). Grype already flagged them on the original. Experiment: they vanish if the package's Maintainer field is NGINX's, so it is a scanner matching artifact. I chose not to copy the maintainer, because that would misattribute our build to F5/NGINX. They concern nginx 1.3.x and older.
- CVE-2026-107494 (HIGH on libssl3) has no fix in bookworm. It is in OpenSSL's QUIC code, and libssl 3.0.x exports no QUIC symbols and nginx imports none, so it is likely not applicable. Not confirmed in the OpenSSL 3.0 source, so it is worded as "likely".
- Scanner databases differ by a day between baseline and rescan, so one CVE appears as "new" through data drift only.

**8. An unexplained test stall.**
The test suite stalled twice at teardown (`docker rm -f` timed out; once the error showed a negative timeout, which points to a host-level pause, not nginx). Not proven. Cleanup now warns instead of failing, with a label on test containers so leftovers can be removed.

**9. Windows host, Linux containers.**
Line endings: CRLF written on Windows broke scripts and flag files inside Linux containers (`.gitattributes` forces LF; scratch files are stripped of `\r`). `make` is not installed on the host, so I verified the same commands directly with `docker build`.

*(Add further difficulties here.)*

## Deliberate differences from the original image

| Difference | Why |
|---|---|
| The 4 dynamic-module packages (geoip, image-filter, njs, xslt) are not built | Scope: core nginx only. The brief allows removing extras. Their libraries are a large part of the baseline CVE count, so this shrinks the image but is not credited as a fix |
| No `curl` or `openssl` CLI in the image | nginx does not need them; they carry many CVEs. `gettext-base` (for the entrypoint's `envsubst`) and `ca-certificates` are kept |
| `.deb` ships core files only: no init scripts, systemd units, logrotate, man page, `nginx-debug` | Meaningless in a container. Listed as exceptions in the layout-parity test, which fails if an exception goes stale or hides a file we do ship |
| `NJS_VERSION` / `NJS_RELEASE` env vars kept | Parity only; njs is not shipped |
| Different `Maintainer` label | Honest attribution, see difficulty 7 |
| Package version identical to upstream (`1.25.5-1~bookworm`) | Matches the brief's heads-up and keeps the VEX demo clean; the VEX document is bound to the image digest and this version string |

## Residual risk

- **nginx itself:** 31 CVEs flagged before, 31 after (Grype CPE mode). I fixed one of them; the rest apply to 1.25.5 and have no patch on the 1.25 branch. Next step: a newer nginx (mainline or stable) is the real fix. Backporting each is not sustainable.
- **CVE-2024-7347:** still flagged by a plain scan because the version string is unchanged; the [VEX file](vex/echo-nginx.openvex.json) removes it for VEX-aware scanners (shown with Grype). Scanners that ignore VEX will still list it.
- **libssl3:** 8 findings remain (4 medium, 3 low, CVE-2026-107494 high, probably not applicable).
- **Base image:** the remaining Trivy findings (1 critical, 39 high) are in Debian packages (libc6, zlib1g CVE-2023-45853 `will_not_fix`, and others), outside what I targeted. Next step: bump one by one with the same method, starting with libpcre2 (already newer in our image) and libc6.
- **Severity inflation:** scanner "Critical" and "High" labels are often higher than the vendors' rating; most OpenSSL items are not reachable through nginx. VEX with `not_affected` justifications is the proper tool for those, once each has its own evidence.
- **Supply chain:** the tarball signing key was compared with the copy on nginx.org, which only shows nginx.org agrees with itself. No independent keyserver check yet. The base image is referenced by tag, not by digest, and the `.deb` build is not verified to be bit-for-bit reproducible.

## Open items

- [x] VEX document, verified on our image and on upstream (see the VEX section).
- [x] Layout-parity test with an explicit list of documented exceptions.
- [ ] A `not_affected` statement for CVE-2026-107494, only after confirming in the OpenSSL 3.0 source that the QUIC code is absent.
- [ ] Run `make image` and `make test` where `make` is installed (the equivalent `docker` commands were verified).
- [ ] Merge the topic branches into `main` and push.

## What surprised me / what I would do differently

- Scanners are blind to nginx.org-built nginx unless told to match by product name, and then only one of the two (Grype) can show a VEX effect.
- The two required fixes explain only a small part of the drop in CVE count. Base image age and removing packages explain most of it.
- A vulnerable build did not crash on my crafted file, so a test for a "crash fix" ended up checking a log message.
- With more time: use a newer nginx, pin the base image by digest, check reproducibility, try a second backport with a real crash reproduction.

## AI tools

I used Claude Code throughout, in a learning mode where I picked each step and approved the plan first.

- **Helped:** writing and testing shell scripts in clean containers, running the scanners and diffing results, gathering advisories and Debian tracker data, and drafting the test harness.
- **Hurt / needed checking:** pages were read through a summarizing helper, so one OpenSSL advisory row (CVE-2024-6119) was based on a summary and had to be re-checked; an early reading of that CVE was corrected. I also made it explain every finding instead of accepting scanner severities.
- **Decisions were mine:** which CVEs, the build layout, the tests' match rules, what to accept as evidence and what to call "likely".

## Repository map

| Path | Content |
|---|---|
| `build/` | `Dockerfile`, `scripts/`, `patches/` (named by CVE), `debian/` packaging, `configure-flags`, pinned `versions.env`, `SHA256SUMS`, signing keys |
| `Containerfile`, `image/` | Final image; upstream's entrypoint files |
| `test/` | Compatibility test, mp4 fixture and tools, nginx configs |
| `baseline/`, `rescan/` | Scan reports of the original and of our image, `rescan/diff.md` |
| `vex/` | OpenVEX document, its generator (`make_vex.py`, `make vex`) and verification (`verify.py`, `verification.md`) |
| `scripts/` | Dev-only helpers (filtering, diffing) |
| `Makefile` | `deb`, `image`, `self-test`, `test`, `clean` |
