# Backported patches

Patches applied to the nginx 1.25.5 source by the build (`patch -p1`, run from the source root).
Each patch is named after the CVE it fixes. Patches taken from upstream are kept byte-for-byte,
with their detached signature next to them, so anyone can re-verify them.

## CVE-2024-7347 - ngx_http_mp4_module

| | |
|---|---|
| Component | `ngx_http_mp4_module` (`ngx_http_mp4_crop_stsc_data`), compiled into the upstream image |
| What it fixes | A specially crafted mp4 file can crash a worker process when the `mp4` directive is used (nginx severity: low) |
| Vulnerable range | 1.5.13 - 1.27.0 (so 1.25.5 is affected) |
| Fixed upstream in | 1.27.1 (mainline), 1.26.2 (stable) |
| Technique | Backport: upstream's official patch applied onto 1.25.5, no version bump |
| Advisory | https://nginx.org/en/security_advisories.html |
| Patch source | https://nginx.org/download/patch.2024.mp4.txt |
| Signature | `CVE-2024-7347.patch.asc` (from `patch.2024.mp4.txt.asc`) |
| Signer | Sergey Kandaurov, fingerprint `D6786CE303D9A9022998DC6CC8464D549AF75C0A`, key in `build/keys/pluknet.key` |
| SHA-256 of the patch | `69d9e5ee112ce0a31a90d48e78af64734d9bbfcf577eeb896f925ba6d795a6b9` |

What the patch changes (reading of the diff): the seek code multiplied two 32-bit values from the file
(`(next_chunk - chunk) * samples`), which can wrap around; it now uses 64-bit arithmetic. It also rejects
a `stsc` table whose chunk numbers go backwards, logging `unordered mp4 stsc chunks`.

### Verify

```sh
gpg --import build/keys/pluknet.key          # use a throwaway GNUPGHOME
gpg --verify build/patches/CVE-2024-7347.patch.asc build/patches/CVE-2024-7347.patch
sha256sum build/patches/CVE-2024-7347.patch   # must equal the SHA-256 above
```

### Checked so far

- Signature verified with a keyring holding only `pluknet.key` (good signature, expected fingerprint).
- Applies cleanly with `patch -p1` to a freshly fetched, verified `nginx-1.25.5` tree.
- The patched `ngx_http_mp4_module.c` compiles (`-Werror`) in a throwaway `debian:bookworm-slim` container.
- Not yet done: the full build, and the compat tests against the built image (`test/compat_test.py`,
  `Mp4PatchVerification`). We could not make unpatched nginx crash with our crafted file, so the evidence for
  this fix is the new log message, not a prevented crash.
