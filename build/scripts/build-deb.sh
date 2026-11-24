#!/usr/bin/env bash
# Compile the (already patched) nginx source tree and package it as a .deb.
#
# Usage: build-deb.sh SRC_DIR OUT_DIR       -> OUT_DIR/nginx_<version>_amd64.deb
# SRC_DIR is the unpacked source after apply-patches.sh. Uses build/configure-flags (upstream's flags),
# `make install` into a staging tree, rearranges it to match upstream's package layout, and builds the
# package with dpkg-deb using the metadata in build/debian/. Fails closed on any error.
set -euo pipefail

BUILD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log() { printf '[build-deb] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

[ $# -eq 2 ] || die "usage: build-deb.sh SRC_DIR OUT_DIR"
SRC="$(cd "$1" && pwd)" || die "source directory not found: $1"
mkdir -p "$2"
OUT="$(cd "$2" && pwd)"
for tool in gcc make dpkg-deb strip md5sum; do
  command -v "$tool" >/dev/null || die "required tool not found: $tool (run install-deps.sh)"
done

# shellcheck source=../versions.env
. "$BUILD_DIR/versions.env"
PKG_VERSION="${NGINX_VERSION}-1~bookworm"   # identical to upstream's package version
DEB="$OUT/nginx_${PKG_VERSION}_amd64.deb"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ROOT="$WORK/root"

# Run a noisy step quietly; show the tail of its log only if it fails.
run() {
  local name="$1"; shift
  log "$name"
  "$@" >"$WORK/$name.log" 2>&1 || { tail -n 40 "$WORK/$name.log" >&2; die "$name failed"; }
}

# 1. Configure with upstream's flags. Each line of configure-flags is one argument.
mapfile -t FLAGS < <(grep -v '^[[:space:]]*\(#\|$\)' "$BUILD_DIR/configure-flags")
for i in "${!FLAGS[@]}"; do
  case "${FLAGS[$i]}" in
    --with-cc-opt=*) FLAGS[$i]="${FLAGS[$i]} -ffile-prefix-map=$SRC=." ;;   # no build paths in the binary
  esac
done
cd "$SRC"
run configure ./configure "${FLAGS[@]}"
run compile make -j"$(nproc)"
run install make install DESTDIR="$ROOT"

# 2. Rearrange `make install` output into upstream's package layout.
log "arranging files"
install -d "$ROOT/usr/share/nginx" "$ROOT/usr/lib/nginx/modules" "$ROOT/var/cache/nginx" \
           "$ROOT/var/log/nginx" "$ROOT/etc/nginx/conf.d"
mv "$ROOT/etc/nginx/html" "$ROOT/usr/share/nginx/html"
# Things upstream's package does not ship: *.default copies, fastcgi.conf and the unused charset maps.
rm -f "$ROOT"/etc/nginx/*.default "$ROOT"/etc/nginx/fastcgi.conf \
      "$ROOT"/etc/nginx/koi-utf "$ROOT"/etc/nginx/koi-win "$ROOT"/etc/nginx/win-utf
# Package-specific configs (not in the tarball) come from build/debian/conf.
install -m 644 "$BUILD_DIR/debian/conf/nginx.conf"   "$ROOT/etc/nginx/nginx.conf"
install -m 644 "$BUILD_DIR/debian/conf/default.conf" "$ROOT/etc/nginx/conf.d/default.conf"
ln -s /usr/lib/nginx/modules "$ROOT/etc/nginx/modules"
strip --strip-unneeded "$ROOT/usr/sbin/nginx"
# Anything left in the tree is a mistake; list it so a surprise is visible in the build log.
find "$ROOT" -mindepth 1 \( -type f -o -type l \) | sed "s|^$ROOT||" | LC_ALL=C sort | sed 's/^/  /' >&2

# 3. Normalise permissions (upstream: dirs 755, files 644, the binary 755, all root-owned).
find "$ROOT" -type d -exec chmod 755 {} +
find "$ROOT" -type f -exec chmod 644 {} +
chmod 755 "$ROOT/usr/sbin/nginx"

# 4. Package metadata and dpkg-deb.
log "assembling $(basename "$DEB")"
install -d -m 755 "$ROOT/DEBIAN"
INSTALLED_SIZE="$(du -sk --exclude=DEBIAN "$ROOT" | cut -f1)"
sed -e "s|@VERSION@|$PKG_VERSION|" -e "s|@INSTALLED_SIZE@|$INSTALLED_SIZE|" \
    "$BUILD_DIR/debian/control" > "$ROOT/DEBIAN/control"
install -m 755 "$BUILD_DIR/debian/preinst"    "$ROOT/DEBIAN/preinst"
install -m 644 "$BUILD_DIR/debian/conffiles"  "$ROOT/DEBIAN/conffiles"
(cd "$ROOT" && find . -type f ! -path './DEBIAN/*' -printf '%P\0' | LC_ALL=C sort -z | xargs -0 md5sum) \
  > "$ROOT/DEBIAN/md5sums"
chmod 644 "$ROOT/DEBIAN/md5sums"
dpkg-deb --root-owner-group --build "$ROOT" "$DEB" >/dev/null
log "built $DEB ($(du -k "$DEB" | cut -f1) KiB)"
dpkg-deb -I "$DEB" | sed -n '/Package:/,/Description:/p' >&2
