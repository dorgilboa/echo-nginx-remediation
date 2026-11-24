# Baseline vs rescan

Baseline = `nginx:1.25-bookworm`; rescan = our image `echo-nginx:test`. Same scanner versions and settings.

## Trivy (default)

| | Findings | By severity |
|---|---|---|
| Baseline | 960 | critical 21, high 238, medium 349, low 275, unknown 77 |
| Rescan | 268 | critical 1, high 39, medium 114, low 97, unknown 17 |

Gone: **694**, still present: 266, **new in rescan: 2**.

Packages that lost the most findings: libheif1 (73), libcurl4 (52), curl (52), openssl (48), libssl3 (48), libexpat1 (43), libtiff6 (33), libk5crypto3 (30)

New in the rescan (package: count): nginx (2)

## Grype (default, Debian tracker)

| | Findings | By severity |
|---|---|---|
| Baseline | 890 | critical 56, high 309, medium 313, low 46, negligible 139, unknown 27 |
| Rescan | 253 | critical 2, high 62, medium 101, low 20, negligible 68 |

Gone: **639**, still present: 251, **new in rescan: 2**.

Packages that lost the most findings: libcurl4 (52), curl (52), openssl (48), libssl3 (48), libexpat1 (43), libheif1 (34), libtiff6 (33), libk5crypto3 (30)

New in the rescan (package: count): libssl3 (1), openssl (1)

## Grype (CPE matching on, sees nginx's own CVEs)

| | Findings | By severity |
|---|---|---|
| Baseline | 920 | critical 63, high 318, medium 327, low 46, negligible 139, unknown 27 |
| Rescan | 288 | critical 9, high 71, medium 118, low 22, negligible 68 |

Gone: **634**, still present: 286, **new in rescan: 2**.

Packages that lost the most findings: libcurl4 (52), curl (52), libssl3 (48), openssl (43), libexpat1 (43), libheif1 (34), libtiff6 (33), libk5crypto3 (30)

New in the rescan (package: count): libssl3 (1), openssl (1)

## The OpenSSL bump (libssl3), per CVE, Trivy

| CVE | Baseline | Rescan |
|---|---|---|
| CVE-2026-31789 | critical, fixed in 3.0.19-1~deb12u2 | gone |
| CVE-2024-6119 | high, fixed in 3.0.14-1~deb12u2 | gone |
| CVE-2025-15467 | high, fixed in 3.0.18-1~deb12u2 | gone |
| CVE-2025-69421 | high, fixed in 3.0.18-1~deb12u2 | gone |
| CVE-2026-28387 | high, fixed in 3.0.19-1~deb12u2 | gone |
| CVE-2026-28388 | high, fixed in 3.0.19-1~deb12u2 | gone |
| CVE-2026-28389 | high, fixed in 3.0.19-1~deb12u2 | gone |
| CVE-2026-28390 | high, fixed in 3.0.19-1~deb12u2 | gone |
| CVE-2026-45447 | high, fixed in 3.0.20-1~deb12u2 | gone |
| CVE-2026-84782 | high, fixed in 3.0.22-1~deb12u2 | gone |

libssl3 findings left in the rescan: CVE-2025-27587 (low), CVE-2026-107493 (low), CVE-2026-107494 (high), CVE-2026-107496 (medium), CVE-2026-121481 (low), CVE-2026-121482 (medium), CVE-2026-84786 (medium), CVE-2026-95690 (medium)

## nginx's own CVEs (Grype with CPE matching)

nginx findings: baseline 31, rescan 31 (the version string is unchanged, so scanners keep flagging every nginx CVE, including the one we patched).

CVE-2024-7347 (our backport): baseline flagged, rescan **still flagged** -> needs the VEX document.

## Anything new or worse?

- Trivy (default): 2 new findings, 2 with a higher severity.
- Grype (default, Debian tracker): 2 new findings, 0 with a higher severity.
- Grype (CPE matching on, sees nginx's own CVEs): 2 new findings, 0 with a higher severity.

## Why findings disappeared (Trivy default, attributed with the package lists)

Image content (deb packages): baseline 149, rescan 93; removed 56, added 0, version changed 47, unchanged 46.

| Cause | Findings gone |
|---|---|
| package removed from the image | 496 |
| package still installed, version changed | 198 |

Removed packages with findings (top): libheif1 (73), libcurl4 (52), curl (52), libexpat1 (43), libtiff6 (33), libk5crypto3 (30), libkrb5support0 (30), libgssapi-krb5-2 (30), libxml2 (30), libkrb5-3 (30)

Targeted libraries (installed version before -> after): libssl3 3.0.11-1~deb12u2 -> 3.0.22-1~deb12u2, libpcre2-8-0 10.42-1 -> 10.42-1+deb12u2, zlib1g 1:1.2.13.dfsg-1 -> 1:1.2.13.dfsg-1, libc6 2.36-9+deb12u7 -> 2.36-9+deb12u14

Debian base: baseline reports Debian 12.5, rescan Debian 12.15 (a newer point release alone fixes many library CVEs, so the totals above are not all our work).

## Scanner database dates (the two scans ran about a day apart)

- Grype baseline: database built 2026-11-23T06:28:32Z
- Grype rescan: database built 2026-11-24T06:22:05Z
- Trivy: the database is fetched fresh on each run; its date is not recorded in the report.
- Effect: a CVE published in between can appear as 'new' (e.g. CVE-2026-107494 on libssl3 in Grype; re-scanning upstream with the newer database flags it there too).
