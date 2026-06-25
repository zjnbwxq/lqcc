from __future__ import annotations

import bz2
import lzma
import zlib

try:  # optional but installed on most modern AI/dev boxes
    import zstandard as zstd  # type: ignore
except Exception:  # pragma: no cover
    zstd = None

try:
    import brotli  # type: ignore
except Exception:  # pragma: no cover
    brotli = None

SUPPORTED_CODECS = {"none", "zlib", "zlib9", "lzma", "bz2", "zstd", "brotli"}
DEFAULT_CODEC = "zlib9"  # dependency-free default; zstd/brotli are optional


def compress_bytes(raw: bytes, codec: str) -> bytes:
    if codec == "none":
        return raw
    if codec == "zlib":
        return zlib.compress(raw, level=6)
    if codec == "zlib9":
        return zlib.compress(raw, level=9)
    if codec == "lzma":
        return lzma.compress(raw, preset=6)
    if codec == "bz2":
        return bz2.compress(raw, compresslevel=9)
    if codec == "zstd":
        if zstd is None:
            raise ValueError("zstd codec requested but zstandard is not installed")
        return zstd.ZstdCompressor(level=12).compress(raw)
    if codec == "brotli":
        if brotli is None:
            raise ValueError("brotli codec requested but brotli is not installed")
        return brotli.compress(raw, quality=8)
    raise ValueError(f"Unsupported codec: {codec}")


def decompress_bytes(blob: bytes, codec: str) -> bytes:
    if codec == "none":
        return blob
    if codec in {"zlib", "zlib9"}:
        return zlib.decompress(blob)
    if codec == "lzma":
        return lzma.decompress(blob)
    if codec == "bz2":
        return bz2.decompress(blob)
    if codec == "zstd":
        if zstd is None:
            raise ValueError("zstd codec requested but zstandard is not installed")
        return zstd.ZstdDecompressor().decompress(blob)
    if codec == "brotli":
        if brotli is None:
            raise ValueError("brotli codec requested but brotli is not installed")
        return brotli.decompress(blob)
    raise ValueError(f"Unsupported codec: {codec}")


def compress_text(text: str, codec: str) -> bytes:
    return compress_bytes(text.encode("utf-8"), codec)


def decompress_text(blob: bytes, codec: str) -> str:
    return decompress_bytes(blob, codec).decode("utf-8")
