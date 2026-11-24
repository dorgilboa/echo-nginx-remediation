# Echo - Build It, Patch It, Ship It

A drop-in replacement for `nginx:1.25-bookworm` (nginx 1.25.5), compiled from source on `debian:bookworm-slim`, with two CVE fixes done end to end (a library version bump and a backported patch), a VEX document, and an automated test that compares it against the original.

I had not done vulnerability remediation on container images before, so this README also records how I worked it out, what went wrong, and what I still would not claim.

## At a glance

| | Original | Mine |
|---|---|---|
| Image | `nginx:1.25-bookworm` | `echo-nginx:test` |
| Size | 273.1 MB | 130.3 MB |
| nginx | 1.25.5, nginx.org package | 1.25.5, compiled from the nginx.org tarball |
| OpenSSL (`libssl3`) | 3.0.11-1~deb12u2 | 3.0.22-1~deb12u2 |
| CVE-2024-7347 (mp4 module) | present | patched in the source |
| Compatibility test | - | 25 of 25 pass |

- **Fix 1, version bump:** `libssl3`, the TLS library nginx links. One bump clears ten findings.
- **Fix 2, backport:** CVE-2024-7347 in nginx's mp4 module. nginx fixed it in 1.27.1 but not for 1.25.5, so I applied nginx's official patch to 1.25.5.

## Build and test

Needs Docker with BuildKit, `make` and Python 3. Run from the repo root.

```bash
make deb        # clean debian:bookworm-slim -> verify source -> patch -> compile -> dist/nginx_1.25.5-1~bookworm_amd64.deb
make image      # install the .deb into a minimal Debian image: echo-nginx:test
make self-test  # upstream compared with upstream; must pass, it proves the test itself works
make test       # upstream vs my image; exits non-zero on any mismatch
make vex        # regenerate the VEX document for the built image
```

`make deb` runs these steps inside `build/Dockerfile`, with no pre-built binaries:

1. `install-deps.sh` installs the compiler and `-dev` libraries from Debian and stops if `libssl-dev` is older than 3.0.22-1~deb12u2.
2. `get-sources.sh` downloads the 1.25.5 tarball from nginx.org, checks its PGP signature against a pinned key fingerprint and its SHA-256 against `build/SHA256SUMS`, and stops on any mismatch.
3. `apply-patches.sh` applies every `build/patches/CVE-*.patch` with no fuzz and fails if one does not apply cleanly.
4. `build-deb.sh` runs `./configure` with upstream's exact 42 flags, runs `make install` into a staging folder and builds the package with `dpkg-deb`.

The `Containerfile` creates the `nginx` user with uid/gid 101 (as upstream) *before* installing the `.deb`, then adds upstream's entrypoint scripts, log symlinks, port 80, stop signal and CMD.

On my Windows machine `make` is not installed. I ran the commands it wraps by hand (`docker build ...`, `python test/compat_test.py`) and checked the Makefile with `make -n`, which prints exactly those commands.

## How I picked the CVEs

The original has 960 findings in Trivy and 890 in Grype (`baseline/`), mostly in base-image libraries. To narrow it down:

1. **What does nginx really use?** An SBOM lists what is installed, not what is loaded, so the check was `ldd` on the binary: libc6, libcrypt1, zlib1g, libpcre2 and libssl3. `libssl3` had the most serious findings.
2. **Only fixable HIGH/CRITICAL.** A bump needs a fixed version to move to (`scripts/filter-baseline.sh` makes this view).
3. **Check the severity.** Scanners score the worst case for the library. OpenSSL's own advisories rate most of these as Low, and none is on nginx's normal TLS handshake path. A "Critical" label is not the same as being exploitable in my image.
4. **Confirm the target version** on the Debian security tracker, because Debian's version numbers differ from OpenSSL's own: `3.0.22-1~deb12u2` includes all ten fixes.

## Fixed CVEs

Severity is the scanner's rating, then the vendor's own where it differs (OpenSSL's advisories, nginx's advisory page).

| CVE | Where | Severity | Fix | Evidence |
|---|---|---|---|---|
| CVE-2026-31789 | libssl3, hex printing of huge certificate fields | Critical / OpenSSL: Low (32-bit only) | bump | [rescan/diff.md](rescan/diff.md) |
| CVE-2024-6119 | libssl3, X.509 name check | High / Moderate | bump | [rescan/diff.md](rescan/diff.md) |
| CVE-2025-15467 | libssl3, CMS parsing | High / High | bump | [rescan/diff.md](rescan/diff.md) |
| CVE-2025-69421 | libssl3, PKCS#12 parsing | High / Low | bump | [rescan/diff.md](rescan/diff.md) |
| CVE-2026-28387 | libssl3, DANE client | High / Low | bump | [rescan/diff.md](rescan/diff.md) |
| CVE-2026-28388 | libssl3, delta CRL | High / Low | bump | [rescan/diff.md](rescan/diff.md) |
| CVE-2026-28389 | libssl3, CMS | High / Low | bump | [rescan/diff.md](rescan/diff.md) |
| CVE-2026-28390 | libssl3, CMS | High / Low | bump | [rescan/diff.md](rescan/diff.md) |
| CVE-2026-45447 | libssl3, `PKCS7_verify` | High / High | bump | [rescan/diff.md](rescan/diff.md) |
| CVE-2026-84782 | libssl3, DTLS | High / High (nginx has no DTLS) | bump | [rescan/diff.md](rescan/diff.md), [vex/verification.md](vex/verification.md) |
| CVE-2024-7347 | nginx mp4 module | Medium (Grype) / nginx: low | **backport** | [patch](build/patches/CVE-2024-7347.patch), [provenance](build/patches/README.md), [tests](test/compat_test.py), [vex/verification.md](vex/verification.md) |

None of the ten OpenSSL CVEs sits on the path nginx uses for normal TLS (CMS, PKCS, DANE, CRL and DTLS code), so I do not claim the bump stopped a real attack on nginx. It is the right hygiene, and the scanners' counts show it. The OpenSSL ratings come from OpenSSL's advisory page, which I read through a summarizing tool; the CVE-2024-6119 row was only available as a summary, so treat it as unconfirmed.

**Removals do not count.** Many more findings are gone only because I removed packages (`curl`, and the libraries the four dynamic modules pulled in, such as libheif, libtiff and libxml2). The brief does not credit that, and I do not either.

## Results of the rescan

Same scanners and settings as the baseline (`rescan/`, full comparison in [rescan/diff.md](rescan/diff.md)).

| | Baseline | Mine |
|---|---|---|
| Trivy | 960 findings (21 critical, 238 high) | 268 (1 critical, 39 high) |
| Grype | 890 | 253 |
| Trivy, fixable HIGH/CRITICAL | - | 0 |

Where the 694 disappeared Trivy findings come from: **496** are packages no longer in the image, and **198** are packages whose version changed. That includes a newer Debian base (12.15 instead of 12.5), so the two real fixes explain only part of the drop. The baseline and rescan ran a day apart and the scanner databases differ, so a few findings appear "new" through data drift alone.

## The backport and the VEX

CVE-2024-7347 is a bug in how the mp4 module reads the `stsc` table of an mp4 file when a client seeks with `?start=`. nginx publishes a signed patch for it. Its signature was verified, it applies cleanly to a freshly verified 1.25.5 tree, and the patched file compiles with `-Werror`; `build/patches/README.md` has the details.

A backport changes the code, not the version string (`1.25.5-1~bookworm`), and scanners match on name and version, so Grype keeps reporting the CVE. That is what a **VEX** (Vulnerability Exploitability eXchange) file is for: a signed-off statement saying a CVE is `fixed` or `not_affected` in a given product. [`vex/echo-nginx.openvex.json`](vex/echo-nginx.openvex.json) has four statements:

| CVE | Status | Reason |
|---|---|---|
| CVE-2024-7347 | fixed | the backport above |
| CVE-2026-84782 | fixed | Debian's `libssl3` 3.0.22-1~deb12u2 has the fix; Grype compares against upstream OpenSSL numbering (fixed in 3.0.23) and still matches |
| CVE-2013-0337 | not affected | about world-readable log files; here the logs are symlinks to `/dev/stdout` and `/dev/stderr` |
| CVE-2009-4487 | not affected | about escape sequences in logs; in a test nginx logged them as the text `\x1B`, not as raw bytes |

The file is **generated** (`make vex`), because my package keeps upstream's version string: a statement that named only the package would also describe the original's still-vulnerable package. Testing showed it does hide findings on the original. So each statement is tied to my image's digest, with the packages as sub-components, and has to be regenerated after a rebuild.

`vex/verify.py` scans with and without the VEX on my image and on upstream ([vex/verification.md](vex/verification.md)). In Grype all four CVEs disappear on my image and **stay flagged on upstream**. Trivy only shows the two old CVEs going away: it cannot see nginx's own CVEs, so the backported CVE can only be shown with Grype.

## The compatibility test

`test/compat_test.py` (Python, standard library only) starts the original and my image as two containers, sends the same requests to both, and exits non-zero on any difference.

**"Working correctly" means:** the same status line, the same body and the same headers, apart from `Date`, `ETag` and `Last-Modified`, which only get sanity checks because they legitimately differ. The 25 tests cover:

- default page, 404, custom config, large body (413), malformed request line, bad HTTP version, over-long URI
- HTTPS with TLS 1.2 and 1.3 and the ALPN choice
- mp4 seeking: whole file, `?start=1`, `?start=1.5`
- file layout: every nginx-related file has the same type, mode, owner and link target as the original, except a written list of deviations. A second test fails if an exception matches nothing upstream has, or hides something I ship
- image metadata (user, ports, entrypoint, CMD), `nginx -V` flags, hashes of the config and entrypoint files
- **fix checks, my image only:** `libssl3` is at least 3.0.22-1~deb12u2 and linked by nginx; the patched mp4 code logs `unordered mp4 stsc chunks` for a crafted file and the worker keeps answering

The test came before the image: `make self-test` (original against original) passes, the empty skeleton image fails because nginx is not running, and an unpatched copy of the original fails exactly the two fix tests. That shows the tests can fail.

**Not covered:** file contents beyond the hashed configs, HTTP/3, the mail and stream modules, performance, and config files other than the ones in `test/conf/`.

## Where I hit a wall

1. **The scanners found no nginx CVEs.** Trivy reported nothing for nginx and Grype two ancient ones, because both match nginx.org's build against *Debian's* tracker, and Debian ships a different nginx. Without a fix there would have been nothing to remove and nothing for a VEX to hide. Grype's CPE mode (`GRYPE_MATCH_DPKG_USING_CPES=true`) flags 29 nginx CVEs (`baseline/baseline-grype-cpe.*`), so I use it for the baseline, the rescan and the VEX demonstration. Trivy has no equivalent: `--detection-priority comprehensive` still found nothing. Even CPE mode missed 9 of the 38 CVEs nginx lists for 1.25.5, so nginx's own advisory page is the real reference.
2. **The original would not crash.** There is no public exploit file, so a valid mp4 was generated (random-noise H.264, `ffmpeg`) and its `stsc` table rewritten out of order. The original answers it with HTTP 500 and the message `start time is out mp4 stco chunks`, with no crash. So the test asserts the new log line from the patched check, and I do not claim the patch prevented a crash.
3. **Patch fuzz.** The first version of `apply-patches.sh` accepted a patch whose context had been deliberately corrupted, because `patch` tolerates mismatching lines by default. Fixed with `-F0`.
4. **Two "new" findings in Trivy.** My package is flagged for CVE-2009-4487 and CVE-2013-0337 (old, low), and the original is not. A test showed Trivy skips them when the package's Maintainer field is NGINX's. Copying that would credit my build to F5, so I left it, documented them and covered them in the VEX.
5. **A test run that stalled.** Twice, container cleanup took far longer than normal and once reported a negative timeout, which points to the host pausing and not to nginx. I could not prove the cause, so cleanup now only warns, and test containers carry a label so leftovers can be found.
6. **Windows and Linux.** Files written on Windows had CRLF line endings that broke flag files inside Linux containers. `.gitattributes` forces LF and scratch files get `\r` stripped.

## Differences from the original image

| Difference | Why |
|---|---|
| The four dynamic-module packages (geoip, image-filter, njs, xslt) are not built | Scope: core nginx only. The brief allows removing extras, with no credit as a fix |
| No `curl` or `openssl` command line tool; `gettext-base` and `ca-certificates` kept | nginx does not need them; `gettext-base` is needed by the entrypoint's `envsubst` |
| No init scripts, systemd units, logrotate config, man page or `nginx-debug` binary | They do nothing in a container; each is an exception in the layout test |
| `NJS_VERSION` and `NJS_RELEASE` variables kept | Parity only; njs is not shipped |
| `Maintainer` and image label are mine | Honest attribution (see wall 4) |
| Package version identical to upstream | Matches what the brief describes, and keeps the VEX demonstration clear |

## Residual risk and next steps

- **nginx itself:** Grype (CPE mode) flags the same 31 nginx findings before and after; 15 of them are HIGH or CRITICAL. I fixed one. The others have no patch for the 1.25 branch. The real fix is a newer nginx release, not backporting each one.
- **CVE-2024-7347:** a plain scan still lists it, since the version did not change. Scanners that ignore VEX will too.
- **libssl3:** Trivy lists 8 findings (CVE-2026-107494 high, 4 medium, 3 low). Grype also rates CVE-2026-107493, -107496 and -84786 as High; OpenSSL fixed them in 3.0.24, which Debian had not shipped when I scanned. CVE-2026-107494 is in OpenSSL's QUIC code; libssl 3.0.11 exports no QUIC symbols and nginx imports none, so it is probably not applicable. I have not confirmed that in the OpenSSL 3.0 source, so I did not write a VEX statement for it.
- **Severity labels:** most scanner "Critical" and "High" ratings are higher than the vendors' and many are not reachable through nginx. `not_affected` VEX statements are the right tool, but only with evidence for each one.
- **Supply chain:** the tarball is verified against the signing key published on nginx.org, which does not prove the key is genuine; there was no independent check. The base image is referenced by tag, not digest, and the `.deb` was not tested for building identically twice.
- **Next:** pin the base image by digest, move to a newer nginx, confirm the QUIC question in the source, and try a second backport with a real reproduction.

## Working process

I worked in small steps, deciding each one before it was built, and kept each change on its own branch merged into `main`: source fetch, CVE triage, scans, backport, `.deb` packaging, image, tests, VEX. The test harness came before the image, and each new script was run in a clean `debian:bookworm-slim` container before I trusted it, including a deliberate failure case (a corrupted patch, a wrong checksum, a broken copy of the image). A work log was kept locally as I went.

## What surprised me / what I would do differently

- Scanners miss nginx.org-built nginx unless told to match by product name, and only Grype can then show a VEX effect.
- A scanner's severity is not the same as risk. The "Critical" in my table is Low according to OpenSSL.
- The two fixes are a small part of the drop in finding counts; the older base image and removed packages account for most of it.
- With the identical version string, a VEX written about the package would also have hidden the original's vulnerability. VEX scope matters.
- With more time I would test with a real crash reproduction, pin the base image, and check the build for reproducibility.

## AI tools

I used **Claude Code** for most of the implementation and investigation, in a mode where it asks me to decide at each step. It wrote the shell scripts, the Python test and VEX generator, and the first drafts of this README, and it ran the scanners, container checks and comparisons. I picked the CVEs and techniques, the match rules for the test, what counted as evidence, and what to call "likely", and I approved each step before it was built.

**Helped:** fast, repeatable checks in clean containers; reading advisories and the Debian tracker; finding problems in its own work with negative tests.

**Needed correcting:**
- an early reading treated CVE-2024-6119 as relevant to nginx, and the advisory summary said otherwise;
- a first VEX table said "not flagged -> gone" for something that was never flagged;
- the first `apply-patches.sh` accepted a corrupted patch (wall 3);
- advisory pages were read through a summarizing step, so some rows rest on summaries, noted above.

## Repository map

| Path | Content |
|---|---|
| `build/` | `Dockerfile`, `scripts/`, `patches/` (named by CVE), `debian/` packaging, `configure-flags`, pins (`versions.env`, `SHA256SUMS`, `keys/`) |
| `Containerfile`, `image/` | The final image and upstream's entrypoint scripts |
| `test/` | Compatibility test, mp4 fixture and tools, nginx configs |
| `baseline/`, `rescan/` | Scan reports of the original and of my image; `rescan/diff.md` |
| `vex/` | VEX document, its generator and verification |
| `scripts/` | Dev-only helpers for filtering and diffing scans |
