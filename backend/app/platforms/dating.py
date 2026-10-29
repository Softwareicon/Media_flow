from __future__ import annotations

from ..schemas import AnalysisStatus, Alternative, Capabilities, DownloadMode
from .base import AdapterContext, AdapterResult, PlatformAdapter


class DatingAppsAdapter(PlatformAdapter):
    """Tinder, Bumble, Hinge and similar. No third-party media access exists; profiles are private."""

    key = "dating"
    name = "Dating apps (Tinder, Bumble, Hinge)"
    domains = ("tinder.com", "gotinder.com", "bumble.com", "hinge.co", "match.com", "okcupid.com")
    download_mode = DownloadMode.EXPORT_ONLY
    capabilities = Capabilities(official_download=False, api_access=False, user_authorized_export=True,
                                direct_media_urls=False)
    media_types = ["image"]
    summary = "Not supported. These services offer no media API; you can only export your own data from them."
    limitations = [
        "Profiles and photos are private to the service and its members.",
        "No official API gives third-party apps access to profile media.",
    ]
    alternatives = [
        Alternative(label="Download your own data",
                    description="Each of these apps has a 'Download my data' or 'Request my data' option in its "
                                "account or privacy settings. It includes the photos you uploaded."),
    ]

    async def analyze(self, url: str, ctx: AdapterContext) -> AdapterResult:
        return self.link_only(
            url,
            "Dating apps don't let other apps retrieve profile photos — they're private to the service. You can "
            "export your own photos using the app's data-download option.",
            status=AnalysisStatus.EXPORT_ONLY, media_type="image",
        )
