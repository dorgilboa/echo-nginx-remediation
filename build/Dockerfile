# Build stage: compiles nginx 1.25.5 from source into a .deb. This image is a factory, it is never shipped.
#
# SKELETON: the real steps come later, in this order (scripts live in build/scripts/):
#   1. install-deps.sh   install the compiler and -dev packages from Debian
#   2. get-sources.sh    fetch the pinned nginx tarball and verify it (PGP + SHA-256)
#   3. apply-patches.sh  apply build/patches/CVE-*.patch
#   4. build-deb.sh      configure, make, package into a .deb
# Must start from a clean debian:bookworm-slim with no pre-baked binaries.
FROM debian:bookworm-slim
