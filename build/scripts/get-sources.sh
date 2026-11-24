#!/usr/bin/env bash
# Fetch the pinned nginx source tarball, verify it, and unpack it.
#
# Usage: get-sources.sh [DEST_DIR]      (default: build/src)
# Fails closed: any problem -> message on stderr, nothing left in DEST_DIR, exit 1.
set -euo pipefail

BUILD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$BUILD_DIR/src}"

log() { printf '[get-sources] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

for tool in curl gpg sha256sum tar; do
  command -v "$tool" >/dev/null || die "required tool not found: $tool"
done

# Load the pins (NGINX_VERSION, NGINX_BASE_URL, NGINX_SIGNING_KEY_FILE, NGINX_SIGNING_KEY_FPR).
# shellcheck source=../versions.env
. "$BUILD_DIR/versions.env"

TARBALL="nginx-${NGINX_VERSION}.tar.gz"

# Work in a temp dir; it is removed on exit, so a failed run leaves nothing behind.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# 1. Download the tarball and its detached signature from the one pinned source.
log "downloading $TARBALL and signature from $NGINX_BASE_URL"
curl -fsSL --retry 3 -o "$WORK/$TARBALL"     "$NGINX_BASE_URL/$TARBALL"     || die "download failed: $TARBALL"
curl -fsSL --retry 3 -o "$WORK/$TARBALL.asc" "$NGINX_BASE_URL/$TARBALL.asc" || die "download failed: $TARBALL.asc"

# 2. Verify the PGP signature using a throwaway keyring that holds only our pinned key.
export GNUPGHOME="$WORK/gnupg"
mkdir -m 700 "$GNUPGHOME"
gpg --batch --quiet --import "$BUILD_DIR/$NGINX_SIGNING_KEY_FILE" 2>/dev/null \
  || die "could not import $NGINX_SIGNING_KEY_FILE"

# The committed key file must really be the key we pinned by fingerprint.
gpg --batch --with-colons --list-keys 2>/dev/null | awk -F: '$1=="fpr"{print $10}' \
  | grep -qx "$NGINX_SIGNING_KEY_FPR" \
  || die "key file does not contain pinned fingerprint $NGINX_SIGNING_KEY_FPR"

# VALIDSIG's last field is the fingerprint of the primary key that signed.
SIGNER="$(gpg --batch --status-fd 1 --verify "$WORK/$TARBALL.asc" "$WORK/$TARBALL" 2>/dev/null \
  | awk '$2=="VALIDSIG"{print $NF}')" || true
[ -n "$SIGNER" ] || die "PGP signature check FAILED for $TARBALL"
[ "$SIGNER" = "$NGINX_SIGNING_KEY_FPR" ] || die "signed by unexpected key $SIGNER"
log "PGP signature OK (signer $SIGNER)"

# 3. Verify the SHA-256 against the committed pin.
PIN="$(grep -F "  $TARBALL" "$BUILD_DIR/SHA256SUMS" || true)"
[ -n "$PIN" ] || die "no checksum for $TARBALL in build/SHA256SUMS"
(cd "$WORK" && echo "$PIN" | sha256sum -c --quiet -) || die "SHA-256 mismatch for $TARBALL"
log "SHA-256 OK"

# 4. Unpack into DEST (only reached if both checks passed).
mkdir -p "$DEST"
rm -rf "${DEST:?}/nginx-${NGINX_VERSION}"
tar -xzf "$WORK/$TARBALL" -C "$DEST" --no-same-owner
log "unpacked to $DEST/nginx-${NGINX_VERSION}"
