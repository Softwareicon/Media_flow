"""Platform capability registry: URL → adapter, and the /platforms listing."""
from __future__ import annotations

from urllib.parse import urlsplit

from .base import AdapterContext, AdapterError, AdapterResult, PlatformAdapter, UnsupportedLink
from .dating import DatingAppsAdapter
from .generic import GenericWebAdapter
from .meta import FacebookAdapter, InstagramAdapter
from .pinterest import PinterestAdapter
from .reddit import RedditAdapter
from .tiktok import TikTokAdapter
from .vimeo import VimeoAdapter
from .x import XAdapter
from .youtube import YouTubeAdapter

# Order matters: specific platforms first, the generic web adapter last.
ADAPTERS: list[PlatformAdapter] = [
    YouTubeAdapter(), InstagramAdapter(), FacebookAdapter(), TikTokAdapter(), XAdapter(), PinterestAdapter(),
    RedditAdapter(), VimeoAdapter(), DatingAppsAdapter(), GenericWebAdapter(),
]
BY_KEY = {a.key: a for a in ADAPTERS}


def adapter_for(url: str) -> PlatformAdapter:
    host = (urlsplit(url).hostname or "").lower()
    for adapter in ADAPTERS:
        if adapter.matches(host):
            return adapter
    return BY_KEY["web"]


__all__ = ["ADAPTERS", "BY_KEY", "adapter_for", "AdapterContext", "AdapterError", "AdapterResult",
           "PlatformAdapter", "UnsupportedLink"]
