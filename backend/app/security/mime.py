"""Magic-byte MIME detection. The server never trusts a Content-Type header on its own.

The same table is mirrored in mobile/src/lib/fileSignature.ts and run on the device
against the downloaded file before it is saved to the photo library.
"""
from __future__ import annotations

SUPPORTED = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/heic": "heic",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/flac": "flac",
}

# Signatures of things that must never be saved as "media".
DANGEROUS_PREFIXES = {
    b"MZ": "windows_executable",
    b"\x7fELF": "elf_executable",
    b"PK\x03\x04": "zip_archive",  # also apk/jar/docx
    b"Rar!": "rar_archive",
    b"7z\xbc\xaf\x27\x1c": "7z_archive",
    b"%PDF": "pdf",
    b"\xca\xfe\xba\xbe": "mach_o",
    b"\xcf\xfa\xed\xfe": "mach_o",
    b"#!": "script",
}


def sniff(head: bytes) -> str | None:
    """Return the detected media MIME, or None if not a supported media file."""
    if len(head) < 4:
        return None
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "video/webm"  # Matroska/WebM container
    if head[:4] == b"OggS":
        return "audio/ogg"
    if head[:4] == b"fLaC":
        return "audio/flac"
    if head[:3] == b"ID3" or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"avif", b"avis"):
            return "image/avif"
        if brand in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
            return "image/heic"
        if brand == b"qt  ":
            return "video/quicktime"
        if brand in (b"M4A ", b"M4B "):
            return "audio/mp4"
        return "video/mp4"
    return None


def dangerous_kind(head: bytes) -> str | None:
    stripped = head.lstrip()
    for prefix, kind in DANGEROUS_PREFIXES.items():
        if head.startswith(prefix):
            return kind
    low = stripped[:64].lower()
    if low.startswith((b"<!doctype", b"<html", b"<?xml", b"<svg", b"<script")):
        return "markup"  # an HTML/SVG page posing as media (SVG can carry script)
    return None


def compatible(declared: str, detected: str) -> bool:
    """Declared Content-Type vs sniffed type. Containers share signatures, so compare families."""
    if not declared or declared == "application/octet-stream":
        return True
    if declared == detected:
        return True
    aliases = {
        "image/jpg": "image/jpeg",
        "image/pjpeg": "image/jpeg",
        "audio/mp3": "audio/mpeg",
        "audio/x-m4a": "audio/mp4",
        "video/x-m4v": "video/mp4",
        "audio/x-wav": "audio/wav",
        "audio/webm": "video/webm",
    }
    d = aliases.get(declared, declared)
    if d == detected:
        return True
    # mp4 family: video/mp4, audio/mp4, quicktime all use ISO-BMFF
    iso = {"video/mp4", "audio/mp4", "video/quicktime"}
    return d in iso and detected in iso


def extension_for(mime: str) -> str:
    return SUPPORTED.get(mime, "bin")
