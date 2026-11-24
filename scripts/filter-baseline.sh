#!/usr/bin/env bash
# Dev-only helper: re-scan an image keeping only the findings that matter for this assignment.
#
# Filter logic (chosen by the learner):
#   1. fixed  - a fixed version exists upstream, so a bump or backport target exists
#   2. severe - severity is in $SEV (default HIGH,CRITICAL)
# The raw, unfiltered baselines (baseline/baseline-*.{txt,json}) are left untouched as evidence.
#
# Run inside the dev image with the docker socket mounted. Usage: filter-baseline.sh [IMAGE]
set -euo pipefail

IMAGE="${1:-nginx:1.25-bookworm}"
OUT="${OUT:-baseline}"
SEV="${SEV:-HIGH,CRITICAL}"

echo "[filter] image=$IMAGE severity=$SEV fixed-only, grype CPE matching=${GRYPE_MATCH_DPKG_USING_CPES:-true}" >&2

trivy image --quiet --severity "$SEV" --ignore-unfixed "$IMAGE" > "$OUT/filtered-trivy.txt"
trivy image --quiet --severity "$SEV" --ignore-unfixed --format json -o "$OUT/filtered-trivy.json" "$IMAGE"

# grype has no severity flag, so it filters fixed-only natively and severity in Python.
# CPE matching: by default Grype matches deb packages only against Debian's tracker, which knows
# nothing about nginx.org-built nginx. With CPE matching it also checks NVD, so nginx's own CVEs show up.
# Keep this identical for the baseline and the rescan so the two can be diffed.
# (Trivy has no equivalent, so its nginx findings stay empty.)
export GRYPE_MATCH_DPKG_USING_CPES="${GRYPE_MATCH_DPKG_USING_CPES:-true}"
grype "$IMAGE" --only-fixed -o json > "$OUT/.grype-fixed.json"
python3 - "$OUT" "$SEV" <<'PY'
import json, sys
out, sev = sys.argv[1], {s.lower() for s in sys.argv[2].split(",")}
m = json.load(open(f"{out}/.grype-fixed.json", encoding="utf-8"))["matches"]
rows = sorted(
    (x["vulnerability"]["severity"], x["vulnerability"]["id"], x["artifact"]["name"],
     x["artifact"]["version"], ",".join(x["vulnerability"]["fix"].get("versions", [])))
    for x in m if x["vulnerability"]["severity"].lower() in sev)
with open(f"{out}/filtered-grype.txt", "w", encoding="utf-8") as f:
    f.write(f"{'SEVERITY':9} {'CVE':18} {'PACKAGE':22} {'INSTALLED':24} FIXED-IN\n")
    for r in rows:
        f.write(f"{r[0]:9} {r[1]:18} {r[2]:22} {r[3]:24} {r[4]}\n")
print(f"[filter] grype: {len(rows)} findings kept", file=sys.stderr)

# Trivy view limited to what nginx links (see LOG.md): one line per CVE with its title.
t = json.load(open(f"{out}/filtered-trivy.json", encoding="utf-8"))
pk = {"libssl3", "libpcre2-8-0", "zlib1g", "libc6", "libcrypt1"}
with open(f"{out}/filtered-nginx-linked.txt", "w", encoding="utf-8") as f:
    for r in t["Results"]:
        for v in r.get("Vulnerabilities") or []:
            if v["PkgName"] in pk:
                f.write(f"{v['Severity']:9} {v['VulnerabilityID']:16} {v['PkgName']:13} "
                        f"{v['InstalledVersion']} -> {v.get('FixedVersion')}\n    {v.get('Title','')}\n")
print("[filter] wrote filtered-nginx-linked.txt (libraries nginx links)", file=sys.stderr)
PY
rm -f "$OUT/.grype-fixed.json"
