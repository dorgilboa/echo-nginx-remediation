#!/usr/bin/env bash
# Install everything the nginx build needs, from Debian bookworm packages.
# Run as root inside a clean debian:bookworm-slim (build/Dockerfile does this).
#
# Besides installing, it enforces the OpenSSL dependency bump: libssl-dev (and so the libssl3 that
# nginx is built against) must be at least MIN_LIBSSL. The newest bookworm-security version is
# installed; if Debian ever served something older, the build fails instead of shipping unfixed.
set -euo pipefail

# First libssl3 version with the fixes for the libssl3 CVEs in our triage (Debian security tracker).
MIN_LIBSSL="${MIN_LIBSSL:-3.0.22-1~deb12u2}"

log() { printf '[install-deps] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root"

PACKAGES=(
  # fetch and verify the pinned nginx source (get-sources.sh)
  curl gnupg ca-certificates
  # apply the backported patches (apply-patches.sh)
  patch
  # compile nginx
  gcc make libc6-dev
  # the three libraries nginx links against (found with ldd on the upstream binary)
  libpcre2-dev zlib1g-dev libssl-dev
  # build the .deb: dpkg-deb / dpkg-shlibdeps, and root-owned files without being root
  dpkg-dev fakeroot
)

export DEBIAN_FRONTEND=noninteractive
log "installing ${#PACKAGES[@]} packages (no recommends)"
apt-get update -qq
apt-get install -y -qq --no-install-recommends "${PACKAGES[@]}"
rm -rf /var/lib/apt/lists/*

# Enforce the OpenSSL bump for both the headers we compile against and the runtime library.
for pkg in libssl-dev libssl3; do
  have="$(dpkg-query -W -f='${Version}' "$pkg")"
  dpkg --compare-versions "$have" ge "$MIN_LIBSSL" \
    || die "$pkg is $have, older than the required $MIN_LIBSSL (is bookworm-security enabled?)"
done

# Record exact versions so the build log shows what the .deb was built with.
log "installed versions:"
dpkg-query -W -f='  ${Package} ${Version}\n' \
  curl gnupg ca-certificates patch gcc make libc6-dev libpcre2-dev zlib1g-dev libssl-dev libssl3 dpkg-dev fakeroot >&2
log "OK (libssl >= $MIN_LIBSSL)"
