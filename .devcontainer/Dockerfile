# Dev/remediation workstation: Debian bookworm + build toolchain + scanners.
FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

# Enable deb-src so `apt-get source` / `build-dep` work (bookworm uses deb822 files).
RUN sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential devscripts dpkg-dev debhelper quilt fakeroot \
      git curl wget ca-certificates gnupg make patch diffutils \
      python3 python3-pip python3-venv golang-go \
      jq vim less sudo unzip \
      libpcre2-dev zlib1g-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Security scanners (latest release at image build time; versions recorded in LOG.md).
RUN curl -sSfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin \
 && curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh  | sh -s -- -b /usr/local/bin \
 && curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin
