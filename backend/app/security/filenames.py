"""Safe file names: no path separators, no control chars, no reserved names, bounded length."""
from __future__ import annotations

import re
import unicodedata

_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_BAD = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*‪-‮⁦-⁩]')  # incl. bidi overrides
_WS = re.compile(r"\s+")


def safe_filename(title: str | None, extension: str, *, fallback: str = "media", max_len: int = 80) -> str:
    stem = unicodedata.normalize("NFKC", title or "")
    stem = _BAD.sub(" ", stem)
    stem = _WS.sub(" ", stem).strip(" .-_")
    if not stem or stem.lower() in _RESERVED:
        stem = fallback
    stem = stem[:max_len].rstrip(" .")
    ext = re.sub(r"[^a-z0-9]", "", (extension or "bin").lower())[:5] or "bin"
    return f"{stem}.{ext}"
