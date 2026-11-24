# Image-level files

Files the `Containerfile` copies into the image. They are not part of the `.deb`: upstream's image adds them
in its Dockerfile, on top of nginx.org's package.

| File | Origin |
|---|---|
| `docker-entrypoint.sh`, `docker-entrypoint.d/*` | Copied unchanged from `nginx:1.25-bookworm` (the docker-library nginx image). The compat test checks their sha256 against upstream's, so they must stay byte-identical. |

Copied files (sha256, first 16 hex digits): `docker-entrypoint.sh` 3372fd90162da30d,
`10-listen-on-ipv6-by-default.sh` 8c5d2c912416126c, `15-local-resolvers.envsh` 3659a4a271496f6a,
`20-envsubst-on-templates.sh` 253c8724acff9f5c, `30-tune-worker-processes.sh` 1f068aa49da8df46.

They are shell scripts (LF line endings, mode 755 set by the `Containerfile`) that call `envsubst`
(`gettext-base`) plus standard tools already present in `debian:bookworm-slim`.
