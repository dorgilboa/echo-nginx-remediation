# syntax=docker/dockerfile:1
# Build stage: compiles nginx from source into a .deb. This image is a factory and is never shipped.
# Starts from a clean debian:bookworm-slim with no pre-baked binaries; every step is a script in build/scripts/.
#
#   make deb      (from the repo root)  ->  dist/nginx_<version>_amd64.deb
#
# Build context is build/ itself, so this file can only see the build inputs.
FROM debian:bookworm-slim AS build

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]
WORKDIR /build

# 1. Toolchain and libraries first, in their own layer: it is cached unless install-deps.sh changes.
#    (This is also where the OpenSSL bump is enforced: the build fails if libssl is too old.)
COPY scripts/install-deps.sh scripts/install-deps.sh
RUN bash scripts/install-deps.sh

# 2. Build inputs: pins, patches, packaging metadata, the other scripts.
COPY . /build

# 3. Fetch + verify the pinned source, apply the backported patches, compile, package.
#    Each script fails closed, so a failed signature/checksum/patch/compile stops the build here.
RUN . ./versions.env \
 && bash scripts/get-sources.sh /src \
 && bash scripts/apply-patches.sh "/src/nginx-${NGINX_VERSION}" \
 && bash scripts/build-deb.sh "/src/nginx-${NGINX_VERSION}" /out

# Output stage: nothing but the .deb, so `docker build --target deb --output` can export it.
FROM scratch AS deb
COPY --from=build /out/ /
