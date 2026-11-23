#!/usr/bin/env bash
# Print tool versions (paste into LOG.md for reproducibility).
cat /etc/debian_version; trivy --version | head -1; grype version | head -2; syft version | head -2
docker --version; gcc --version | head -1; go version; python3 --version
