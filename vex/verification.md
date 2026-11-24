# VEX verification

VEX file: `vex/echo-nginx.openvex.json`; our image: `echo-nginx:test`; upstream: `nginx:1.25-bookworm`. Each cell: result without the VEX -> with the VEX.

| CVE | Scanner | Our image | Upstream image (must NOT change) |
|---|---|---|---|
| CVE-2024-7347 | Grype | flagged -> gone | flagged -> **still flagged** |
| CVE-2024-7347 | Trivy | never reported (nothing to remove) | never reported (nothing to remove) |
| CVE-2013-0337 | Grype | flagged -> gone | flagged -> **still flagged** |
| CVE-2013-0337 | Trivy | flagged -> gone | never reported (nothing to remove) |
| CVE-2009-4487 | Grype | flagged -> gone | flagged -> **still flagged** |
| CVE-2009-4487 | Trivy | flagged -> gone | never reported (nothing to remove) |
| CVE-2026-84782 | Grype | flagged -> gone | flagged -> **still flagged** |
| CVE-2026-84782 | Trivy | never reported (nothing to remove) | flagged -> **still flagged** |

`never reported` means that scanner does not list the CVE for that image even without the VEX, so the VEX changes nothing there. Trivy has no CPE matching, so it never sees nginx's own CVEs such as CVE-2024-7347; only Grype can show that one disappearing.
