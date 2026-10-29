"""URL validation, platform detection, MIME sniffing, file names."""
from __future__ import annotations

import pytest

from app.platforms import adapter_for
from app.platforms.base import UnsupportedLink, quality_from_height
from app.platforms.meta import fb_video_id, ig_shortcode
from app.platforms.vimeo import video_ref
from app.platforms.x import tweet_id
from app.platforms.youtube import iso_duration, video_id
from app.security import mime
from app.security.filenames import safe_filename
from app.security.netguard import UnsafeURLError
from app.url_tools import extract_url, normalize_url

from .conftest import JPEG_HEAD, MP4_HEAD, PNG_HEAD


# ---------- URL extraction / normalization
def test_extracts_link_from_shared_text():
    assert extract_url("Watch this!! https://youtu.be/dQw4w9WgXcQ?si=abc 🔥") == "https://youtu.be/dQw4w9WgXcQ?si=abc"


def test_bare_domain_gets_https():
    assert extract_url("example.com/video.mp4") == "https://example.com/video.mp4"


@pytest.mark.parametrize("bad", ["", "   ", "not a link", "javascript:alert(1)", "ftp://x.com/a"])
def test_rejects_non_links(bad):
    with pytest.raises(UnsafeURLError):
        normalize_url(bad)


def test_strips_tracking_but_keeps_content_ids():
    out = normalize_url("https://www.YouTube.com/watch?v=dQw4w9WgXcQ&utm_source=x&si=123&fbclid=zz#t=10")
    assert out == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


# ---------- platform detection
@pytest.mark.parametrize("url,key", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
    ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "youtube"),
    ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
    ("https://www.instagram.com/reel/C9abcDEFghi/", "instagram"),
    ("https://www.facebook.com/watch?v=123456789012", "facebook"),
    ("https://fb.watch/abcDEF/", "facebook"),
    ("https://www.tiktok.com/@user/video/7311111111111111111", "tiktok"),
    ("https://vm.tiktok.com/ZMabc123/", "tiktok"),
    ("https://x.com/user/status/1790000000000000000", "x"),
    ("https://twitter.com/user/status/1790000000000000000", "x"),
    ("https://www.pinterest.co.uk/pin/123456789/", "pinterest"),
    ("https://pin.it/abc123", "pinterest"),
    ("https://www.reddit.com/r/pics/comments/abc123/title/", "reddit"),
    ("https://redd.it/abc123", "reddit"),
    ("https://vimeo.com/76979871", "vimeo"),
    ("https://player.vimeo.com/video/76979871?h=abcdef1234", "vimeo"),
    ("https://tinder.com/@someone", "dating"),
    ("https://cdn.example.org/clip.mp4", "web"),
    # look-alike domains must NOT be treated as the platform
    ("https://youtube.com.evil.net/watch?v=dQw4w9WgXcQ", "web"),
    ("https://notyoutube.com/watch?v=dQw4w9WgXcQ", "web"),
    ("https://instagram.com-login.example/p/abc", "web"),
])
def test_platform_detection(url, key):
    assert adapter_for(url).key == key


def test_youtube_ids():
    assert video_id("https://youtu.be/dQw4w9WgXcQ") == ("dQw4w9WgXcQ", False)
    assert video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == ("dQw4w9WgXcQ", True)
    assert video_id("https://www.youtube.com/embed/dQw4w9WgXcQ")[0] == "dQw4w9WgXcQ"
    for bad in ("https://www.youtube.com/@channel", "https://www.youtube.com/watch?v=short", "https://www.youtube.com/"):
        with pytest.raises(UnsupportedLink):
            video_id(bad)
    assert iso_duration("PT1H2M3S") == 3723 and iso_duration("P1DT1S") == 86401 and iso_duration("junk") is None


def test_other_platform_ids():
    assert ig_shortcode("https://www.instagram.com/p/C9abcDEFghi/") == "C9abcDEFghi"
    assert ig_shortcode("https://www.instagram.com/someuser/reel/C9abcDEFghi/") == "C9abcDEFghi"
    assert fb_video_id("https://www.facebook.com/somepage/videos/123456789012/") == "123456789012"
    assert fb_video_id("https://www.facebook.com/reel/987654321098") == "987654321098"
    assert tweet_id("https://x.com/a/status/1790000000000000000/photo/1") == "1790000000000000000"
    assert video_ref("https://vimeo.com/76979871/abcdef1234") == ("76979871", "abcdef1234")
    assert video_ref("https://player.vimeo.com/video/76979871?h=abcdef1234") == ("76979871", "abcdef1234")
    with pytest.raises(UnsupportedLink):
        ig_shortcode("https://www.instagram.com/someuser/")


def test_quality_labels_never_inflate():
    assert quality_from_height(1080) == "1080p"
    assert quality_from_height(2160) == "4K"
    assert quality_from_height(1012) == "1080p"  # 1920x1012 letterboxed counts as 1080p
    assert quality_from_height(900) == "720p"  # rounds DOWN to the standard it actually meets
    assert quality_from_height(None) is None


# ---------- MIME / file safety
def test_sniff_signatures():
    assert mime.sniff(MP4_HEAD) == "video/mp4"
    assert mime.sniff(JPEG_HEAD) == "image/jpeg"
    assert mime.sniff(PNG_HEAD) == "image/png"
    assert mime.sniff(b"\x1a\x45\xdf\xa3" + b"\x00" * 20) == "video/webm"
    assert mime.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert mime.sniff(b"ID3\x04\x00" + b"\x00" * 10) == "audio/mpeg"
    assert mime.sniff(b"MZ\x90\x00" + b"\x00" * 30) is None


@pytest.mark.parametrize("head,kind", [(b"MZ\x90\x00", "windows_executable"), (b"PK\x03\x04", "zip_archive"),
                                       (b"\x7fELF", "elf_executable"), (b"  <!DOCTYPE html>", "markup"),
                                       (b"<svg onload=x>", "markup"), (b"%PDF-1.7", "pdf")])
def test_dangerous_content_detected(head, kind):
    assert mime.dangerous_kind(head) == kind


def test_type_spoofing_detected():
    assert mime.compatible("video/mp4", "video/mp4")
    assert mime.compatible("image/jpg", "image/jpeg")
    assert mime.compatible("video/mp4", "video/quicktime")  # same ISO-BMFF family
    assert not mime.compatible("image/png", "video/mp4")
    assert not mime.compatible("video/mp4", "image/jpeg")


def test_safe_filenames():
    assert safe_filename("../../etc/passwd", "mp4") == "etc passwd.mp4"
    assert safe_filename("CON", "jpg") == "media.jpg"
    assert safe_filename("evil‮gnp.exe", "png") == "evil gnp.exe.png"  # bidi override removed, ext forced
    assert safe_filename("a" * 300, "mp4").endswith(".mp4") and len(safe_filename("a" * 300, "mp4")) <= 84
    assert safe_filename("", "MP4!") == "media.mp4"
    assert safe_filename('My "cool" video: part 1/2', "webm") == "My cool video part 1 2.webm"
