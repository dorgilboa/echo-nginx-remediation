"""Tiny mp4 helper for the CVE-2024-7347 test: rewrite the `stsc` (sample-to-chunk) table of a valid file.

An mp4 is a tree of "boxes": 4-byte big-endian size, 4-byte type, payload. The seek code patched by
CVE-2024-7347 (ngx_http_mp4_crop_stsc_data) reads the `stsc` box, which lists entries of
(first_chunk, samples_per_chunk, sample_description_index). Valid files list first_chunk in ascending
order; the patch rejects a table where it goes backwards.

How test/fixtures/valid.mp4 was made (random noise video, so it is valid but not copied from anywhere):
    ffmpeg -f lavfi -i "nullsrc=s=48x48:r=10:d=2,geq=lum=random(1)*255:cb=128:cr=128" \
           -c:v libx264 -pix_fmt yuv420p -crf 35 -g 5 -an valid.mp4

Limits (enough for our fixture): 32-bit box sizes only, and `moov` must come after `mdat`
(ffmpeg's default), because then growing `moov` does not shift the chunk offsets.
"""
from __future__ import annotations

import struct

CONTAINERS = {"moov", "trak", "mdia", "minf", "stbl"}


def _walk(data: bytes, start: int, end: int, path: tuple = ()):
    """Yield (offset, size, type, ancestor_offsets) for every box, descending into container boxes."""
    i = start
    while i + 8 <= end:
        size, raw_type = struct.unpack(">I4s", data[i:i + 8])
        typ = raw_type.decode("latin-1")
        if size < 8:
            raise ValueError(f"unsupported box size {size} for {typ!r} at offset {i}")
        yield i, size, typ, path
        if typ in CONTAINERS:
            yield from _walk(data, i + 8, i + size, path + (i,))
        i += size


def find_stsc(data: bytes) -> tuple[int, int, tuple]:
    """Return (offset, size, ancestor_offsets) of the first stsc box."""
    for off, size, typ, path in _walk(data, 0, len(data)):
        if typ == "stsc":
            return off, size, path
    raise ValueError("no stsc box found")


def read_stsc(data: bytes) -> list[tuple[int, int, int]]:
    off, _, _ = find_stsc(data)
    count = struct.unpack(">I", data[off + 12:off + 16])[0]
    return [struct.unpack(">III", data[off + 16 + 12 * k:off + 28 + 12 * k]) for k in range(count)]


def set_stsc(data: bytes, entries: list[tuple[int, int, int]]) -> bytes:
    """Return a copy of `data` whose stsc table is `entries`, with all enclosing box sizes fixed up."""
    top = [typ for _, _, typ, path in _walk(data, 0, len(data)) if not path and typ in ("moov", "mdat")]
    if top and top[0] != "mdat":
        raise ValueError("moov precedes mdat: chunk offsets would need shifting; use a non-faststart file")
    off, size, ancestors = find_stsc(data)
    payload = b"\0\0\0\0" + struct.pack(">I", len(entries)) + b"".join(struct.pack(">III", *e) for e in entries)
    delta = len(payload) - (size - 8)
    out = bytearray(data[:off + 8] + payload + data[off + size:])
    for pos in (*ancestors, off):
        out[pos:pos + 4] = struct.pack(">I", struct.unpack(">I", out[pos:pos + 4])[0] + delta)
    return bytes(out)


def unordered_stsc(data: bytes) -> bytes:
    """The malformed case from CVE-2024-7347: the second entry's first_chunk is lower than the first's."""
    return set_stsc(data, [(10, 1, 1), (1, 1, 1)])
