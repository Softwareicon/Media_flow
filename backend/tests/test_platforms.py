"""Per-platform adapter behaviour against MOCKED API responses shaped like each platform's public docs.
These prove our parsing and policy logic; they are not live integration tests."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx

from app.platforms import reddit as reddit_mod

from .conftest import JPEG_HEAD, MP4_HEAD, PNG_HEAD, auth


def analyze(c, h, url):
    r = c.post("/api/v1/media/analyze", json={"url": url}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def connect(c, h, platform):
    """Full 3-step flow: start (app) → provider callback (browser) → complete (app, with verifier)."""
    start = c.post(f"/api/v1/connections/{platform}/start", headers=h)
    assert start.status_code == 200, start.text
    state = parse_qs(urlsplit(start.json()["authorize_url"]).query)["state"][0]
    cb = c.get(f"/api/v1/connections/{platform}/callback", params={"code": "the-code", "state": state},
               follow_redirects=False)
    assert cb.status_code == 302
    loc = cb.headers["location"]
    q = parse_qs(urlsplit(loc).query)
    if q.get("status") != ["pending"]:
        return loc
    done = c.post(f"/api/v1/connections/{platform}/complete",
                  json={"handoff": q["handoff"][0], "verifier": start.json()["verifier"]}, headers=h)
    assert done.status_code == 200, done.text
    return "status=connected"


# ---------------- link-only platforms
def test_youtube_is_link_only_with_preview(client, web):
    web.json("www.youtube.com", "/oembed", {"title": "Never Gonna Give You Up", "author_name": "Rick Astley",
                                            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"})
    a = analyze(client, auth(client), "https://youtu.be/dQw4w9WgXcQ?si=tracking")
    assert a["status"] == "link_only" and a["options"] == [] and a["analysis_id"] is None
    assert a["title"] == "Never Gonna Give You Up" and a["author"] == "Rick Astley"
    assert a["official_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert any("Premium" in alt["label"] or "offline" in alt["label"].lower() for alt in a["alternatives"])
    # we only ever talked to YouTube's oEmbed endpoint
    assert {r.headers["host"] for r in web.seen} == {"www.youtube.com"}


def test_youtube_preview_survives_oembed_failure(client, web):
    a = analyze(client, auth(client), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")  # oembed 404s
    assert a["status"] == "link_only" and a["title"] is None and a["official_url"]


def test_tiktok_link_only(client, web):
    web.json("www.tiktok.com", "/oembed", {"title": "dance", "author_name": "creator",
                                           "thumbnail_url": "https://p16.tiktokcdn.com/x.jpg"})
    a = analyze(client, auth(client), "https://www.tiktok.com/@creator/video/7311111111111111111")
    assert a["status"] == "link_only" and a["author"] == "creator" and a["options"] == []


def test_dating_export_only(client):
    a = analyze(client, auth(client), "https://tinder.com/@someone")
    assert a["status"] == "export_only" and a["options"] == [] and a["alternatives"]


# ---------------- X
def test_x_disabled_without_operator_opt_in(make_client, web):
    c = make_client(X_BEARER_TOKEN="tok")  # token present but downloads not enabled
    a = analyze(c, auth(c), "https://x.com/someone/status/1790000000000000000")
    assert a["status"] == "not_configured" and a["options"] == []
    assert not any(r.headers.get("host") == "api.x.com" for r in web.seen)


def test_x_api_photos_and_video_variants(make_client, web):
    c = make_client(X_BEARER_TOKEN="tok", X_MEDIA_DOWNLOADS_ENABLED="true")
    web.json("api.x.com", "/2/tweets/1790000000000000000", {
        "data": {"id": "1790000000000000000", "text": "Look at this", "possibly_sensitive": False},
        "includes": {"users": [{"username": "someone"}], "media": [
            {"type": "video", "preview_image_url": "https://pbs.twimg.com/thumb.jpg", "duration_ms": 10000,
             "variants": [
                 {"content_type": "application/x-mpegURL", "url": "https://video.twimg.com/pl.m3u8"},
                 {"content_type": "video/mp4", "bit_rate": 832000, "url": "https://video.twimg.com/ext_tw_video/1/pu/vid/avc1/640x360/a.mp4"},
                 {"content_type": "video/mp4", "bit_rate": 2176000, "url": "https://video.twimg.com/ext_tw_video/1/pu/vid/avc1/1280x720/b.mp4"},
             ]}]}})
    a = analyze(c, auth(c), "https://twitter.com/someone/status/1790000000000000000")
    assert a["status"] == "downloadable" and a["author"] == "@someone"
    labels = sorted(o["quality_label"] for o in a["options"])
    assert labels == ["360p", "720p"]  # HLS playlist skipped, nothing invented
    best = next(o for o in a["options"] if o["id"] == a["best_option_id"])
    assert best["height"] == 720 and best["size_is_estimate"] and best["size_bytes"] == 2176000 * 10 // 8
    assert web.seen[-1].headers["authorization"] == "Bearer tok"


def test_x_sensitive_posts_refused(make_client, web):
    c = make_client(X_BEARER_TOKEN="tok", X_MEDIA_DOWNLOADS_ENABLED="true")
    web.json("api.x.com", "/2/tweets/1790000000000000001", {"data": {"id": "1", "possibly_sensitive": True}})
    a = analyze(c, auth(c), "https://x.com/a/status/1790000000000000001")
    assert a["status"] == "unavailable" and "sensitive" in a["explanation"]


# ---------------- Vimeo (connected account)
def vimeo_env():
    return {"VIMEO_CLIENT_ID": "cid", "VIMEO_CLIENT_SECRET": "secret"}


def test_vimeo_not_configured_vs_needs_connection(client, make_client, web):
    web.json("vimeo.com", "/api/oembed.json", {"title": "My Film", "author_name": "Me", "duration": 42,
                                               "thumbnail_url": "https://i.vimeocdn.com/video/1.jpg"})
    assert analyze(client, auth(client), "https://vimeo.com/76979871")["status"] == "not_configured"
    c = make_client(**vimeo_env())
    a = analyze(c, auth(c), "https://vimeo.com/76979871")
    assert a["status"] == "needs_connection" and a["title"] == "My Film" and a["duration_seconds"] == 42


def test_vimeo_connect_and_download_renditions(make_client, web):
    c = make_client(**vimeo_env())
    h = auth(c)
    web.json("api.vimeo.com", "/oauth/access_token", {"access_token": "user-token", "scope": "public private video_files",
                                                      "user": {"uri": "/users/42", "name": "Me"}})
    assert "status=connected" in connect(c, h, "vimeo")
    tok_req = next(r for r in web.seen if r.url.path == "/oauth/access_token")
    assert tok_req.headers["authorization"].startswith("Basic ")  # secret sent only to Vimeo
    acct = c.get("/api/v1/account", headers=h).json()
    assert acct["connections"] == ["vimeo"]
    web.json("api.vimeo.com", "/videos/76979871", {
        "name": "My Film", "duration": 42, "user": {"name": "Me"},
        "pictures": {"sizes": [{"width": 640, "link": "https://i.vimeocdn.com/s.jpg"},
                               {"width": 1920, "link": "https://i.vimeocdn.com/l.jpg"}]},
        "download": [
            {"quality": "sd", "rendition": "540p", "type": "video/mp4", "width": 960, "height": 540, "size": 10_000_000,
             "link": "https://player.vimeo.com/play/1?s=a", "expires": "2099-01-01T00:00:00+00:00"},
            {"quality": "source", "rendition": "source", "type": "video/mp4", "width": 3840, "height": 2160,
             "size": 900_000_000, "link": "https://player.vimeo.com/play/2?s=b", "expires": "2099-01-01T00:00:00+00:00"},
        ]})
    a = analyze(c, h, "https://vimeo.com/76979871")
    assert a["status"] == "downloadable" and a["thumbnail_url"] == "https://i.vimeocdn.com/l.jpg"
    assert sorted(o["quality_label"] for o in a["options"]) == ["540p", "Original"]
    best = next(o for o in a["options"] if o["id"] == a["best_option_id"])
    assert best["is_original"] and best["width"] == 3840 and best["size_bytes"] == 900_000_000
    assert web.seen[-1].headers["authorization"] == "bearer user-token"
    t = c.post("/api/v1/downloads", json={"analysis_id": a["analysis_id"], "option_id": best["id"]}, headers=h)
    assert t.json()["media_url"] == "https://player.vimeo.com/play/2?s=b"
    # disconnect removes the token; next analysis needs a connection again
    assert c.delete("/api/v1/connections/vimeo", headers=h).status_code == 204
    web.json("vimeo.com", "/api/oembed.json", {"title": "My Film"})
    assert analyze(c, h, "https://vimeo.com/76979871")["status"] == "needs_connection"


def test_vimeo_not_owner_gets_no_files(make_client, web):
    c = make_client(**vimeo_env())
    h = auth(c)
    web.json("api.vimeo.com", "/oauth/access_token", {"access_token": "t", "user": {"uri": "/users/1"}})
    connect(c, h, "vimeo")
    web.json("api.vimeo.com", "/videos/111111", {"name": "Someone else's", "download": []})
    a = analyze(c, h, "https://vimeo.com/111111")
    assert a["status"] == "link_only" and "own" in a["explanation"]


def test_oauth_state_is_single_use_and_bound(make_client, web):
    c = make_client(**vimeo_env())
    h = auth(c)
    web.json("api.vimeo.com", "/oauth/access_token", {"access_token": "t"})
    start = c.post("/api/v1/connections/vimeo/start", headers=h).json()
    state = parse_qs(urlsplit(start["authorize_url"]).query)["state"][0]
    assert "redirect_uri=https%3A%2F%2Fapi.mediaflow.test%2Fapi%2Fv1%2Fconnections%2Fvimeo%2Fcallback" in start["authorize_url"]
    bad = c.get("/api/v1/connections/vimeo/callback", params={"code": "x", "state": "forged"}, follow_redirects=False)
    assert "status=expired" in bad.headers["location"]
    wrong_platform = c.get("/api/v1/connections/pinterest/callback", params={"code": "x", "state": state},
                           follow_redirects=False)
    assert "status=" in wrong_platform.headers["location"] and "pending" not in wrong_platform.headers["location"]
    # state burned by the wrong-platform attempt → replay fails too
    replay = c.get("/api/v1/connections/vimeo/callback", params={"code": "x", "state": state}, follow_redirects=False)
    assert "status=expired" in replay.headers["location"]


def test_oauth_link_sent_to_victim_cannot_attach_victims_token(make_client, web):
    """Attacker starts a flow and tricks a victim into approving it. The victim's token must never be
    attached to the attacker's account (review finding: OAuth state not bound to the initiating app)."""
    c = make_client(**vimeo_env())
    attacker, victim = auth(c), auth(c)
    web.json("api.vimeo.com", "/oauth/access_token", {"access_token": "VICTIM-TOKEN", "user": {"uri": "/users/9"}})
    start = c.post("/api/v1/connections/vimeo/start", headers=attacker).json()
    state = parse_qs(urlsplit(start["authorize_url"]).query)["state"][0]
    # victim's browser completes the provider consent → handoff goes to the VICTIM's device
    cb = c.get("/api/v1/connections/vimeo/callback", params={"code": "c", "state": state}, follow_redirects=False)
    handoff = parse_qs(urlsplit(cb.headers["location"]).query)["handoff"][0]
    # victim's app tries to complete: wrong user and no verifier → refused
    r = c.post("/api/v1/connections/vimeo/complete", json={"handoff": handoff, "verifier": "x" * 43}, headers=victim)
    assert r.status_code == 403
    # attacker even with their verifier can't use the (now burned) handoff
    r2 = c.post("/api/v1/connections/vimeo/complete", json={"handoff": handoff, "verifier": start["verifier"]},
                headers=attacker)
    assert r2.status_code == 403
    assert c.get("/api/v1/account", headers=attacker).json()["connections"] == []
    assert c.get("/api/v1/account", headers=victim).json()["connections"] == []


def test_complete_requires_matching_verifier(make_client, web):
    c = make_client(**vimeo_env())
    h = auth(c)
    web.json("api.vimeo.com", "/oauth/access_token", {"access_token": "t"})
    start = c.post("/api/v1/connections/vimeo/start", headers=h).json()
    state = parse_qs(urlsplit(start["authorize_url"]).query)["state"][0]
    cb = c.get("/api/v1/connections/vimeo/callback", params={"code": "c", "state": state}, follow_redirects=False)
    handoff = parse_qs(urlsplit(cb.headers["location"]).query)["handoff"][0]
    bad = c.post("/api/v1/connections/vimeo/complete", json={"handoff": handoff, "verifier": "y" * 43}, headers=h)
    assert bad.status_code == 403
    assert c.get("/api/v1/account", headers=h).json()["connections"] == []


def test_connection_requires_encryption_key(make_client):
    c = make_client(**vimeo_env(), TOKEN_ENCRYPTION_KEY="")
    r = c.post("/api/v1/connections/vimeo/start", headers=auth(c))
    assert r.status_code == 503


# ---------------- Instagram (own professional account)
def test_instagram_own_post_matched(make_client, web):
    c = make_client(INSTAGRAM_APP_ID="app", INSTAGRAM_APP_SECRET="sec")
    h = auth(c)
    assert analyze(c, h, "https://www.instagram.com/p/C9abcDEFghi/")["status"] == "needs_connection"
    web.json("api.instagram.com", "/oauth/access_token", {"access_token": "short", "user_id": 17841})
    web.json("graph.instagram.com", "/access_token", {"access_token": "long", "expires_in": 5_184_000})
    assert "status=connected" in connect(c, h, "instagram")
    web.json("graph.instagram.com", "/me/media", {"data": [
        {"id": "1", "permalink": "https://www.instagram.com/p/OTHERpost11/", "media_type": "IMAGE", "media_url": "https://scontent.cdninstagram.com/o.jpg"},
        {"id": "2", "permalink": "https://www.instagram.com/p/C9abcDEFghi/", "media_type": "CAROUSEL_ALBUM",
         "caption": "Trip", "username": "me", "media_url": "https://scontent.cdninstagram.com/a.jpg",
         "children": {"data": [
             {"media_type": "IMAGE", "media_url": "https://scontent.cdninstagram.com/a.jpg"},
             {"media_type": "VIDEO", "media_url": "https://scontent.cdninstagram.com/b.mp4"}]}}]})
    web.file("scontent.cdninstagram.com", "/a.jpg", JPEG_HEAD, "image/jpeg", total=400_000)
    web.file("scontent.cdninstagram.com", "/b.mp4", MP4_HEAD, "video/mp4", total=8_000_000)
    a = analyze(c, h, "https://www.instagram.com/p/C9abcDEFghi/?igsh=xyz")
    assert a["status"] == "downloadable" and a["media_type"] == "gallery" and a["author"] == "@me"
    assert [(o["kind"], o["size_bytes"]) for o in a["options"]] == [("image", 400_000), ("video", 8_000_000)]
    assert all(o["width"] is None for o in a["options"])  # API gives no dimensions → none invented
    media_req = next(r for r in web.seen if r.url.path == "/me/media")
    assert parse_qs(media_req.url.query.decode())["access_token"] == ["long"]  # long-lived token stored


def test_instagram_someone_elses_post(make_client, web):
    c = make_client(INSTAGRAM_APP_ID="app", INSTAGRAM_APP_SECRET="sec")
    h = auth(c)
    web.json("api.instagram.com", "/oauth/access_token", {"access_token": "short", "user_id": 1})
    web.json("graph.instagram.com", "/access_token", {"access_token": "long"})
    connect(c, h, "instagram")
    web.json("graph.instagram.com", "/me/media", {"data": [], "paging": {}})
    a = analyze(c, h, "https://www.instagram.com/reel/NotMine1234/")
    assert a["status"] == "link_only" and a["options"] == []


# ---------------- Facebook
def test_facebook_owned_video(make_client, web):
    c = make_client(FACEBOOK_APP_ID="app", FACEBOOK_APP_SECRET="sec")
    h = auth(c)
    web.json("graph.facebook.com", "/v21.0/oauth/access_token", {"access_token": "fbtok", "expires_in": 3600})
    connect(c, h, "facebook")
    web.json("graph.facebook.com", "/v21.0/123456789012", {"source": "https://video.xx.fbcdn.net/v.mp4",
                                                           "title": "Launch", "length": 31.5, "from": {"name": "My Page"}})
    web.file("video.xx.fbcdn.net", "/v.mp4", MP4_HEAD, "video/mp4", total=3_000_000)
    a = analyze(c, h, "https://www.facebook.com/mypage/videos/123456789012/")
    assert a["status"] == "downloadable" and a["duration_seconds"] == 31.5 and a["options"][0]["size_bytes"] == 3_000_000
    web.json("graph.facebook.com", "/v21.0/999999999999", {"title": "Not mine"})
    b = analyze(c, h, "https://www.facebook.com/watch?v=999999999999")
    assert b["status"] == "link_only"


# ---------------- Pinterest
def test_pinterest_largest_image_and_video_link_only(make_client, web):
    c = make_client(PINTEREST_APP_ID="app", PINTEREST_APP_SECRET="sec")
    h = auth(c)
    web.json("api.pinterest.com", "/v5/oauth/token", {"access_token": "pt", "refresh_token": "rt", "expires_in": 2592000})
    connect(c, h, "pinterest")
    web.json("api.pinterest.com", "/v5/pins/123456789", {"title": "Kitchen", "media": {"media_type": "image", "images": {
        "150x150": {"width": 150, "height": 150, "url": "https://i.pinimg.com/150x150/a.jpg"},
        "1200x": {"width": 1200, "height": 1600, "url": "https://i.pinimg.com/1200x/a.jpg"}}}})
    web.file("i.pinimg.com", "/1200x/a.jpg", JPEG_HEAD, "image/jpeg", total=250_000)
    a = analyze(c, h, "https://www.pinterest.com/pin/123456789/")
    o = a["options"][0]
    assert a["status"] == "downloadable" and o["width"] == 1200 and o["quality_label"] == "1200px"
    assert not o["is_original"] and "not the original" in o["note"]
    web.json("api.pinterest.com", "/v5/pins/987654321", {"media": {"media_type": "video", "cover_image_url": "https://i.pinimg.com/c.jpg"}})
    v = analyze(c, h, "https://www.pinterest.com/pin/987654321/")
    assert v["status"] == "link_only" and v["options"] == []


# ---------------- Reddit
def reddit_client(make_client, web):
    reddit_mod._token_cache.clear()
    c = make_client(REDDIT_CLIENT_ID="rid", REDDIT_CLIENT_SECRET="rsec")
    web.json("www.reddit.com", "/api/v1/access_token", {"access_token": "app-token", "expires_in": 86400})
    return c


def info(post):
    return {"data": {"children": [{"data": post}]}}


def test_reddit_gallery_images(make_client, web):
    c = reddit_client(make_client, web)
    web.json("oauth.reddit.com", "/api/info", info({
        "title": "My photos", "author": "op", "permalink": "/r/pics/comments/abc123/my_photos/", "is_gallery": True,
        "gallery_data": {"items": [{"media_id": "m1"}, {"media_id": "m2"}, {"media_id": "m3"}]},
        "media_metadata": {
            "m1": {"status": "valid", "e": "Image", "m": "image/jpg", "s": {"x": 4032, "y": 3024}},
            "m2": {"status": "valid", "e": "Image", "m": "image/png", "s": {"x": 1080, "y": 1080}},
            "m3": {"status": "failed", "e": "Image", "m": "image/jpg"}}}))
    web.file("i.redd.it", "/m1.jpg", JPEG_HEAD, "image/jpeg", total=3_000_000)
    web.file("i.redd.it", "/m2.png", PNG_HEAD, "image/png", total=900_000)
    a = analyze(c, auth(c), "https://www.reddit.com/r/pics/comments/abc123/my_photos/")
    assert a["status"] == "downloadable" and a["media_type"] == "gallery"
    assert [(o["width"], o["mime_type"]) for o in a["options"]] == [(4032, "image/jpeg"), (1080, "image/png")]
    info_req = next(r for r in web.seen if r.url.path == "/api/info")
    assert info_req.headers["authorization"] == "bearer app-token"
    assert "mediaflow" in info_req.headers["user-agent"]


def test_reddit_video_link_only_and_nsfw_refused(make_client, web):
    c = reddit_client(make_client, web)
    h = auth(c)
    web.json("oauth.reddit.com", "/api/info", info({"title": "clip", "is_video": True, "permalink": "/r/v/comments/vid111/x/",
                                                    "secure_media": {"reddit_video": {"duration": 12}}}))
    a = analyze(c, h, "https://redd.it/vid111")
    assert a["status"] == "link_only" and "separate" in a["explanation"] and a["duration_seconds"] == 12
    web.json("oauth.reddit.com", "/api/info", info({"title": "x", "over_18": True}))
    assert analyze(c, h, "https://www.reddit.com/comments/nsfw11/")["status"] == "unavailable"


def test_reddit_external_link_post(make_client, web):
    c = reddit_client(make_client, web)
    web.json("oauth.reddit.com", "/api/info", info({"title": "news", "url_overridden_by_dest": "https://news.example/a"}))
    a = analyze(c, auth(c), "https://www.reddit.com/r/news/comments/ext111/news/")
    assert a["status"] == "link_only" and a["alternatives"][0]["url"] == "https://news.example/a"


def test_reddit_media_server_link_rejected(client):
    r = client.post("/api/v1/media/analyze", json={"url": "https://v.redd.it/abcdef"}, headers=auth(client))
    assert r.status_code == 422 and r.json()["code"] == "unsupported_link"


# ---------------- registry
def test_platform_registry_reports_honestly(client):
    h = auth(client)
    plats = {p["key"]: p for p in client.get("/api/v1/platforms", headers=h).json()}
    assert set(plats) == {"youtube", "instagram", "facebook", "tiktok", "x", "pinterest", "reddit", "vimeo",
                          "dating", "web"}
    assert plats["youtube"]["download_mode"] == "link_only" and plats["youtube"]["capabilities"]["api_access"] is False
    assert plats["web"]["configured"] and plats["web"]["capabilities"]["direct_media_urls"]
    for key in ("vimeo", "instagram", "facebook", "pinterest", "reddit", "x"):
        assert plats[key]["configured"] is False, key  # no credentials in this test env → not claimed
    assert plats["dating"]["download_mode"] == "export_only"
    assert all(p["limitations"] or p["key"] == "web" for p in plats.values())


def test_api_never_returns_secrets(make_client, web):
    c = make_client(X_BEARER_TOKEN="super-secret-token", X_MEDIA_DOWNLOADS_ENABLED="true", VIMEO_CLIENT_ID="cid",
                    VIMEO_CLIENT_SECRET="vimeo-secret")
    h = auth(c)
    blob = c.get("/api/v1/platforms", headers=h).text + c.get("/api/v1/connections", headers=h).text
    assert "super-secret-token" not in blob and "vimeo-secret" not in blob
