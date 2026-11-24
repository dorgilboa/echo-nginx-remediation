# syntax=docker/dockerfile:1
# Final image: installs our .deb into a minimal Debian base. This is the image we ship.
# It must be a drop-in for nginx:1.25-bookworm: same user, ports, entrypoint, stop signal and layout.
#
#   make image      (builds dist/nginx_*.deb first, then this file)
FROM debian:bookworm-slim

# Our own maintainer label. (Upstream's names the NGINX Docker maintainers; that is not us.)
LABEL maintainer="Echo nginx remediation build <build@echo.invalid>"

# Same values as nginx:1.25-bookworm. NJS_VERSION / NJS_RELEASE are mirrored only for exact parity:
# the njs module package is NOT shipped in this image (deliberate deviation, see README).
ENV NGINX_VERSION=1.25.5 \
    NJS_VERSION=0.8.4 \
    NJS_RELEASE=3~bookworm \
    PKG_RELEASE=1~bookworm

# 1. The nginx user with upstream's fixed uid/gid 101, created BEFORE the package so the
#    package's preinst finds it and does not pick a different id.
RUN set -eux; \
    groupadd --system --gid 101 nginx; \
    useradd --system --gid nginx --no-create-home --home /nonexistent \
            --comment "nginx user" --shell /bin/false --uid 101 nginx

# 2. Install our .deb. apt resolves its Depends, which includes libssl3 >= 3.0.22-1~deb12u2
#    (the OpenSSL bump). gettext-base provides envsubst for the entrypoint's template feature;
#    ca-certificates lets nginx verify upstream TLS servers. curl and the openssl CLI that
#    upstream ships are deliberately left out: nginx does not use them.
COPY dist/nginx_*.deb /tmp/
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends /tmp/nginx_*.deb gettext-base ca-certificates; \
    rm -rf /var/lib/apt/lists/* /tmp/nginx_*.deb

# 3. Image-level setup that upstream's Dockerfile does (not part of the package):
#    log files go to the container's stdout/stderr, and the entrypoint scripts.
RUN set -eux; \
    mkdir /docker-entrypoint.d; \
    ln -sf /dev/stdout /var/log/nginx/access.log; \
    ln -sf /dev/stderr /var/log/nginx/error.log
COPY --chmod=755 image/docker-entrypoint.sh /
COPY --chmod=755 image/docker-entrypoint.d/ /docker-entrypoint.d/

EXPOSE 80
STOPSIGNAL SIGQUIT
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
