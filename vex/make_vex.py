#!/usr/bin/env python3
"""Generate the OpenVEX document for ONE built image.

Usage: make_vex.py [IMAGE] [--out FILE]        (default image: echo-nginx:test; default output: stdout)

Why a script and not a static file: scanners match nginx by name + version, and our package keeps upstream's
version string (1.25.5-1~bookworm) on purpose. A statement that names only the package would therefore also
describe upstream's still-vulnerable package and wrongly hide its findings (tested: it does). So every statement
is bound to this exact image by its digest, with the packages as sub-components, and the package URLs carry the
image's Debian version. A rebuilt image has a new digest, so the document must be regenerated: `make vex`.

Needs the docker CLI and a locally built image that has a repo digest. Standard library only.
"""
import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone

AUTHOR = "Echo nginx remediation build"
PATCH_SHA = "69d9e5ee112ce0a31a90d48e78af64734d9bbfcf577eeb896f925ba6d795a6b9"


def docker(*args):
    p = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        sys.exit(f"make_vex: `docker {' '.join(args)}` failed: {p.stderr.strip()}")
    return p.stdout


def image_facts(image):
    digests = json.loads(docker("image", "inspect", "-f", "{{json .RepoDigests}}", image))
    if not digests:
        sys.exit(f"make_vex: {image} has no repo digest (build it with `make image`; a digest is assigned on build)")
    repo, _, digest = digests[0].partition("@sha256:")
    debian = docker("run", "--rm", "--entrypoint", "cat", image, "/etc/debian_version").strip()
    pkgs = {}
    out = docker("run", "--rm", "--entrypoint", "dpkg-query", image, "-W",
                 "-f=${Package} ${Version} ${Architecture}\\n", "nginx", "libssl3")
    for line in out.splitlines():
        name, version, arch = line.split()
        pkgs[name] = (version, arch)
    return repo.split("/")[-1], digest, debian, pkgs


def build(image):
    repo, digest, debian, pkgs = image_facts(image)

    def purl(name, source_of=None):
        version, arch = pkgs[source_of or name]
        return f"pkg:deb/debian/{name}@{version}?arch={arch}&distro=debian-{debian}"

    product_id = f"pkg:oci/{repo}@sha256%3A{digest}"

    def products(*purls):
        return [{"@id": product_id, "subcomponents": [{"@id": p} for p in purls]}]

    nginx = purl("nginx")
    statements = [
        {   # the backport: scanners still match because the version string did not change
            "vulnerability": {"name": "CVE-2024-7347"},
            "products": products(nginx),
            "status": "fixed",
            "status_notes": (
                "Backport of nginx's official patch (build/patches/CVE-2024-7347.patch, sha256 " + PATCH_SHA +
                ") applied to nginx 1.25.5; the package version is unchanged, so version-matching scanners "
                "still flag it. Evidence: test/compat_test.py Mp4PatchVerification (the patched check logs "
                "'unordered mp4 stsc chunks'). A crash on the unpatched build was not reproduced."),
        },
        {   # scanner compares against upstream OpenSSL numbering; Debian's build already has the fix
            "vulnerability": {"name": "CVE-2026-84782"},
            "products": products(purl("libssl3"), purl("openssl", source_of="libssl3")),
            "status": "fixed",
            "status_notes": (
                "Debian's security tracker lists the fix in libssl3 3.0.22-1~deb12u2, which is installed. "
                "Some scanners compare against upstream OpenSSL numbering (fixed in 3.0.23) and still match. "
                "The CVE concerns DTLS; the nginx binary imports no DTLS symbols."),
        },
        {
            "vulnerability": {"name": "CVE-2013-0337"},
            "products": products(nginx),
            "status": "not_affected",
            "justification": "inline_mitigations_already_exist",
            "impact_statement": (
                "The CVE describes world-readable access.log/error.log files in the default configuration "
                "(nginx 1.3.13 and earlier). In this image both are symlinks to /dev/stdout and /dev/stderr; "
                "no log files are created. The scanner applies Debian's tracker data for Debian's own nginx "
                "package to nginx.org's package."),
        },
        {
            "vulnerability": {"name": "CVE-2009-4487"},
            "products": products(nginx),
            "status": "not_affected",
            "justification": "inline_mitigations_already_exist",
            "impact_statement": (
                "The CVE (nginx 0.7.64) describes raw terminal escape sequences from requests reaching the log. "
                "nginx 1.25.5's default log format escapes non-printable bytes: in a test, an ESC byte in the "
                "User-Agent and in the request line was logged as the text \\x1B, with no raw ESC byte written."),
        },
    ]
    return {
        "@context": "https://openvex.dev/ns/v0.2.0",
        "@id": "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, product_id)),
        "author": AUTHOR,
        "role": "Document Creator",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": 1,
        "statements": statements,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image", nargs="?", default="echo-nginx:test")
    ap.add_argument("--out")
    args = ap.parse_args()
    data = (json.dumps(build(args.image), indent=2) + "\n").encode("utf-8")   # bytes: no CRLF on Windows
    if args.out:
        with open(args.out, "wb") as f:
            f.write(data)
    else:
        sys.stdout.buffer.write(data)


if __name__ == "__main__":
    main()
