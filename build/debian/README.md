# Package metadata (`build/debian/`)

Input files for `build/scripts/build-deb.sh`, which assembles the `.deb` with `dpkg-deb` (no debhelper).

| File | Purpose |
|---|---|
| `control` | Package name, version, `Depends`. `@VERSION@` and `@INSTALLED_SIZE@` are filled in by the script. `libssl3 (>= 3.0.22-1~deb12u2)` is the OpenSSL dependency bump. |
| `preinst` | Creates the `nginx` system user and group if missing (the image creates uid/gid 101 first). |
| `conffiles` | Config files that dpkg preserves on upgrade; same set as upstream's package. |
| `conf/nginx.conf`, `conf/default.conf` | Package-specific configs. They are not in the nginx source tarball, so they are copied from nginx.org's packaging as shipped in `nginx:1.25-bookworm` (sha256 `078266b9...adec` and `48801b39...777c`, checked by the compat test). |

All other shipped files (`mime.types`, `*_params`, `index.html`, `50x.html`) come from the verified source
tarball; their hashes are identical to upstream's.

## Deliberate deviations from upstream's `nginx` package

Not shipped, because they do nothing in a container: `/etc/init.d/nginx*`, systemd units, `/etc/default/nginx*`,
`/etc/logrotate.d/nginx`, the man page, the `nginx-debug` binary, the `lsb-base` dependency, and the
`postinst`/`prerm`/`postrm` scripts (they only manage the service). The four dynamic-module packages are not built either.
