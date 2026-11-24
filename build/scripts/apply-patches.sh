#!/usr/bin/env bash
# Apply our backported patches (build/patches/CVE-*.patch) to an unpacked nginx source tree.
#
# Usage: apply-patches.sh SRC_DIR [PATCH_DIR]     (PATCH_DIR defaults to build/patches)
# Patches are applied in name order with `patch -p1`, each one dry-run first. Fails closed: a patch that
# does not apply cleanly (wrong version, already applied, drifted code), a missing patch directory, or no
# patches at all stops the build with exit 1. Only source patches belong here; the OpenSSL bump is a
# package version and is enforced in install-deps.sh and the .deb dependencies.
set -euo pipefail

BUILD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-}"
PATCH_DIR="${2:-$BUILD_DIR/patches}"

log() { printf '[apply-patches] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

[ -n "$SRC" ] || die "usage: apply-patches.sh SRC_DIR [PATCH_DIR]"
[ -d "$SRC" ] || die "source directory not found: $SRC"
[ -d "$PATCH_DIR" ] || die "patch directory not found: $PATCH_DIR"
for tool in patch sha256sum; do
  command -v "$tool" >/dev/null || die "required tool not found: $tool"
done

# Name order is apply order. A build that expects a backport must not silently apply nothing.
mapfile -t PATCHES < <(find "$PATCH_DIR" -maxdepth 1 -name 'CVE-*.patch' -type f | LC_ALL=C sort)
[ "${#PATCHES[@]}" -gt 0 ] || die "no CVE-*.patch files in $PATCH_DIR"

for p in "${PATCHES[@]}"; do
  name="$(basename "$p")"
  log "$name (sha256 $(sha256sum "$p" | cut -c1-64))"
  # --forward refuses a patch that looks already applied; -s keeps the output to errors only.
  # -F0 turns off "fuzz": by default `patch` tolerates up to 2 mismatching context lines, which would let a
  # drifted patch land in the wrong place without any error. We want an exact match or a failure.
  patch -d "$SRC" -p1 -F0 --forward --dry-run -s < "$p" || die "$name does not apply cleanly to $SRC (dry run)"
  patch -d "$SRC" -p1 -F0 --forward --no-backup-if-mismatch -s < "$p" || die "$name failed while applying to $SRC"
  log "applied $name"
done

log "OK: ${#PATCHES[@]} patch(es) applied to $SRC"
