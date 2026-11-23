#!/usr/bin/env bash
# Fetch pristine nginx source matching the baseline image (nginx:1.25-bookworm = 1.25.5)
# and the upstream git history (needed to find/backport CVE fixes). Both are gitignored.
set -euo pipefail
cd "$(dirname "$0")/.."
VER="${NGINX_VERSION:-1.25.5}"
mkdir -p src
[ -d src/nginx-git ] || git clone https://github.com/nginx/nginx.git src/nginx-git
if [ ! -d "src/nginx-$VER" ]; then
  curl -sSfL "https://nginx.org/download/nginx-$VER.tar.gz" -o "src/nginx-$VER.tar.gz"
  tar -C src -xzf "src/nginx-$VER.tar.gz"
fi
echo "nginx source ready: src/nginx-$VER and src/nginx-git"
