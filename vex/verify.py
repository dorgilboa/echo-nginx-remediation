#!/usr/bin/env python3
"""Show the VEX at work: scan with and without it, on our image AND on upstream's, print Markdown.

Run inside the dev image (it has grype and trivy) with the docker socket mounted:
  docker run --rm --user root -v /var/run/docker.sock:/var/run/docker.sock -v <repo>:/work -w /work \
      echo-dev-test:latest python3 vex/verify.py [OURS] [UPSTREAM] [VEX_FILE] > vex/verification.md
Grype runs with CPE matching on (needed to see nginx's own CVEs), the same setting as the baseline and rescan.
The table's last two columns are the safety check: upstream must stay flagged, because the VEX describes OUR image only.
"""
import json
import os
import subprocess
import sys

OURS = sys.argv[1] if len(sys.argv) > 1 else "echo-nginx:test"
UPSTREAM = sys.argv[2] if len(sys.argv) > 2 else "nginx:1.25-bookworm"
VEX = sys.argv[3] if len(sys.argv) > 3 else "vex/echo-nginx.openvex.json"
CVES = ["CVE-2024-7347", "CVE-2013-0337", "CVE-2009-4487", "CVE-2026-84782"]
PKGS = {"nginx", "libssl3", "openssl"}   # grype also reports the OpenSSL source package name


def run(cmd, env=None):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env={**os.environ, **(env or {})})
    if p.returncode not in (0, 1):
        sys.exit(f"verify: {' '.join(cmd)} failed: {p.stderr.strip()[:300]}")
    return json.loads(p.stdout)


def grype(image, vex=None):
    cmd = ["grype", image, "-q", "-o", "json"] + (["--vex", vex] if vex else [])
    data = run(cmd, {"GRYPE_MATCH_DPKG_USING_CPES": "true"})
    return {m["vulnerability"]["id"] for m in data["matches"] if m["artifact"]["name"] in PKGS}


def trivy(image, vex=None):
    cmd = ["trivy", "image", "-q", "--format", "json"] + (["--vex", vex] if vex else []) + [image]
    data = run(cmd)
    return {v["VulnerabilityID"] for r in data.get("Results", []) for v in (r.get("Vulnerabilities") or [])
            if v["PkgName"] in PKGS}


def cell(before, after, cve):
    if cve not in before:
        return "never reported (nothing to remove)"
    return "flagged -> " + ("**still flagged**" if cve in after else "gone")


scans = {}
for tool, fn in (("Grype", grype), ("Trivy", trivy)):
    for name, image in (("ours", OURS), ("upstream", UPSTREAM)):
        scans[(tool, name)] = (fn(image), fn(image, VEX))

print("# VEX verification\n")
print(f"VEX file: `{VEX}`; our image: `{OURS}`; upstream: `{UPSTREAM}`. Each cell: result without the VEX -> with the VEX.\n")
print("| CVE | Scanner | Our image | Upstream image (must NOT change) |\n|---|---|---|---|")
for cve in CVES:
    for tool in ("Grype", "Trivy"):
        o, u = scans[(tool, "ours")], scans[(tool, "upstream")]
        print(f"| {cve} | {tool} | {cell(*o, cve)} | {cell(*u, cve)} |")
print("\n`never reported` means that scanner does not list the CVE for that image even without the VEX, "
      "so the VEX changes nothing there. Trivy has no CPE matching, so it never sees nginx's own CVEs "
      "such as CVE-2024-7347; only Grype can show that one disappearing.")
