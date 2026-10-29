"""End-to-end API tests (mocked upstreams — see conftest)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from .conftest import JPEG_HEAD, MP4_HEAD, auth


def analyze(c, h, url):
    return c.post("/api/v1/media/analyze", json={"url": url}, headers=h)


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["database"] is True
    assert r.headers["x-content-type-options"] == "nosniff"


def test_auth_required(client):
    assert client.post("/api/v1/media/analyze", json={"url": "https://a.example/x.mp4"}).status_code == 401
    assert client.get("/api/v1/downloads", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_full_direct_download_lifecycle(client, web):
    web.file("cdn.example", "/clips/Holiday%20Trip.mp4", MP4_HEAD, "video/mp4", total=5_242_880)
    h = auth(client)
    r = analyze(client, h, "https://cdn.example/clips/Holiday%20Trip.mp4?utm_source=x")
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["status"] == "downloadable" and a["platform"] == "web" and a["media_type"] == "video"
    opt = a["options"][0]
    assert opt["mime_type"] == "video/mp4" and opt["size_bytes"] == 5_242_880 and opt["is_original"]
    assert a["best_option_id"] == opt["id"] and a["title"] == "Holiday Trip"
    assert "media_url" not in str(a)  # the actual file URL is only released on authorization

    t = client.post("/api/v1/downloads", json={"analysis_id": a["analysis_id"], "option_id": opt["id"]}, headers=h)
    assert t.status_code == 201, t.text
    ticket = t.json()
    assert ticket["media_url"] == "https://cdn.example/clips/Holiday%20Trip.mp4"
    assert ticket["download"]["file_name"] == "Holiday Trip.mp4"
    did = ticket["download"]["id"]

    assert client.patch(f"/api/v1/downloads/{did}", json={"status": "in_progress", "received_bytes": 1000},
                        headers=h).json()["status"] == "in_progress"
    done = client.patch(f"/api/v1/downloads/{did}", json={"status": "completed", "received_bytes": 5_242_880}, headers=h)
    assert done.json()["status"] == "completed" and done.json()["completed_at"]
    assert client.post(f"/api/v1/downloads/{did}/cancel", headers=h).status_code == 409  # already finished
    assert client.get(f"/api/v1/downloads/{did}", headers=h).json()["received_bytes"] == 5_242_880
    assert client.delete(f"/api/v1/downloads/{did}", headers=h).status_code == 204
    assert client.get(f"/api/v1/downloads/{did}", headers=h).status_code == 404


def test_failed_download_records_reason(client, web):
    web.file("cdn.example", "/a.jpg", JPEG_HEAD, "image/jpeg")
    h = auth(client)
    a = analyze(client, h, "https://cdn.example/a.jpg").json()
    did = client.post("/api/v1/downloads", json={"analysis_id": a["analysis_id"], "option_id": "f0"},
                      headers=h).json()["download"]["id"]
    r = client.patch(f"/api/v1/downloads/{did}", json={"status": "failed", "error_code": "insufficient_storage"},
                     headers=h)
    assert r.json()["status"] == "failed" and r.json()["error_code"] == "insufficient_storage"
    bad = client.patch(f"/api/v1/downloads/{did}", json={"status": "failed", "error_code": "DROP TABLE;"}, headers=h)
    assert bad.status_code == 409 or bad.status_code == 422


def test_cancel_in_progress(client, web):
    web.file("cdn.example", "/a.jpg", JPEG_HEAD, "image/jpeg")
    h = auth(client)
    a = analyze(client, h, "https://cdn.example/a.jpg").json()
    did = client.post("/api/v1/downloads", json={"analysis_id": a["analysis_id"], "option_id": "f0"},
                      headers=h).json()["download"]["id"]
    assert client.post(f"/api/v1/downloads/{did}/cancel", headers=h).json()["status"] == "cancelled"


def test_list_search_filter_paginate(client, web):
    h = auth(client)
    for i, name in enumerate(["Beach day", "Mountain hike", "Beach night"]):
        web.file("cdn.example", f"/{name.replace(' ', '_')}.jpg", JPEG_HEAD, "image/jpeg")
        a = analyze(client, h, f"https://cdn.example/{name.replace(' ', '_')}.jpg").json()
        did = client.post("/api/v1/downloads", json={"analysis_id": a["analysis_id"], "option_id": "f0"},
                          headers=h).json()["download"]["id"]
        if i == 1:
            client.patch(f"/api/v1/downloads/{did}", json={"status": "completed"}, headers=h)
    assert len(client.get("/api/v1/downloads", headers=h).json()["items"]) == 3
    assert len(client.get("/api/v1/downloads?q=beach", headers=h).json()["items"]) == 2
    assert len(client.get("/api/v1/downloads?q=%25", headers=h).json()["items"]) == 0  # wildcard is escaped
    assert [d["title"] for d in client.get("/api/v1/downloads?status=completed", headers=h).json()["items"]] == ["Mountain_hike"]
    p1 = client.get("/api/v1/downloads?limit=2", headers=h).json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    p2 = client.get("/api/v1/downloads", params={"limit": 2, "cursor": p1["next_cursor"]}, headers=h).json()
    assert len(p2["items"]) == 1 and p2["next_cursor"] is None
    assert {d["id"] for d in p1["items"]}.isdisjoint({d["id"] for d in p2["items"]})


def test_users_are_isolated(client, web):
    web.file("cdn.example", "/a.jpg", JPEG_HEAD, "image/jpeg")
    alice, bob = auth(client), auth(client)
    a = analyze(client, alice, "https://cdn.example/a.jpg").json()
    assert client.post("/api/v1/downloads", json={"analysis_id": a["analysis_id"], "option_id": "f0"},
                       headers=bob).status_code == 404
    did = client.post("/api/v1/downloads", json={"analysis_id": a["analysis_id"], "option_id": "f0"},
                      headers=alice).json()["download"]["id"]
    assert client.get(f"/api/v1/downloads/{did}", headers=bob).status_code == 404
    assert client.delete(f"/api/v1/downloads/{did}", headers=bob).status_code == 404
    assert client.get("/api/v1/downloads", headers=bob).json()["items"] == []


def test_expired_analysis(web, make_client):
    web.file("cdn.example", "/a.jpg", JPEG_HEAD, "image/jpeg")
    c = make_client(ANALYSIS_TTL_SECONDS="-1")  # analyses expire immediately
    h = auth(c)
    a = analyze(c, h, "https://cdn.example/a.jpg").json()
    r = c.post("/api/v1/downloads", json={"analysis_id": a["analysis_id"], "option_id": "f0"}, headers=h)
    assert r.status_code == 410 and r.json()["code"] == "analysis_expired"


def test_unknown_option(client, web):
    web.file("cdn.example", "/a.jpg", JPEG_HEAD, "image/jpeg")
    h = auth(client)
    a = analyze(client, h, "https://cdn.example/a.jpg").json()
    r = client.post("/api/v1/downloads", json={"analysis_id": a["analysis_id"], "option_id": "zzz"}, headers=h)
    assert r.status_code == 404 and r.json()["code"] == "option_not_found"


def test_size_limit(make_client, web):
    web.file("cdn.example", "/big.mp4", MP4_HEAD, "video/mp4", total=10_000_000)
    c = make_client(MAX_MEDIA_BYTES="1000000")
    h = auth(c)
    a = analyze(c, h, "https://cdn.example/big.mp4").json()
    assert a["status"] == "unavailable" and a["analysis_id"] is None
    assert "limit" in a["explanation"]


def test_expired_or_missing_links(client, web):
    web.on("cdn.example", "/gone.mp4", httpx.Response(404))
    web.on("cdn.example", "/signed.mp4", httpx.Response(403))
    h = auth(client)
    gone = analyze(client, h, "https://cdn.example/gone.mp4").json()
    assert gone["status"] == "unavailable" and "expired" in gone["explanation"]
    signed = analyze(client, h, "https://cdn.example/signed.mp4").json()
    assert signed["status"] == "unavailable" and "expired" in signed["explanation"]
    nodns = analyze(client, h, "https://does-not-exist.example/x.mp4")
    assert nodns.status_code == 422 and nodns.json()["code"] == "dns_failure"


def test_spoofed_and_dangerous_files_rejected(client, web):
    web.file("cdn.example", "/movie.mp4", b"MZ\x90\x00" + b"\x00" * 60, "video/mp4")  # exe posing as mp4
    web.file("cdn.example", "/pic.jpg", MP4_HEAD, "image/png")  # declared png, actually mp4
    web.file("cdn.example", "/x.jpg", b"<!DOCTYPE html><script>", "image/jpeg")
    web.file("cdn.example", "/app.bin", b"PK\x03\x04" + b"\x00" * 60, "application/octet-stream")
    h = auth(client)
    for path, word in (("/movie.mp4", "program"), ("/pic.jpg", "don't match"), ("/x.jpg", "program"),
                       ("/app.bin", "program")):
        a = analyze(client, h, f"https://cdn.example{path}").json()
        assert a["status"] == "unavailable" and a["options"] == [], path
        assert word in a["explanation"], (path, a["explanation"])


def test_streaming_manifests_refused(client, web):
    web.on("cdn.example", "/live.m3u8", httpx.Response(200, content=b"#EXTM3U\n",
                                                        headers={"content-type": "application/vnd.apple.mpegurl"}))
    a = analyze(client, auth(client), "https://cdn.example/live.m3u8").json()
    assert a["status"] == "unavailable" and "streaming" in a["explanation"]


def test_html_page_with_declared_media(client, web):
    page = b"""<html><head><title>Fallback</title>
      <meta property="og:title" content="Sunset Timelapse">
      <meta property="og:video:secure_url" content="https://media.example/sunset.mp4">
      <meta property="og:image" content="/poster.jpg">
      <meta property="og:image:width" content="1920"><meta property="og:image:height" content="1080">
      </head><body><video src="http://10.0.0.8/internal.mp4"></video>
      <video><source src="https://media.example/sunset.webm" type="video/webm"></video></body></html>"""
    web.on("blog.example", "/post", httpx.Response(200, content=page, headers={"content-type": "text/html; charset=utf-8"}))
    web.file("media.example", "/sunset.mp4", MP4_HEAD, "video/mp4", total=9_000_000)
    web.file("media.example", "/sunset.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 60, "video/webm", total=7_000_000)
    web.file("blog.example", "/poster.jpg", JPEG_HEAD, "image/jpeg", total=300_000)
    a = analyze(client, auth(client), "https://blog.example/post").json()
    assert a["status"] == "downloadable" and a["title"] == "Sunset Timelapse" and a["media_type"] == "video"
    kinds = sorted((o["mime_type"], o["size_bytes"]) for o in a["options"])
    assert kinds == [("image/jpeg", 300_000), ("video/mp4", 9_000_000), ("video/webm", 7_000_000)]
    img = next(o for o in a["options"] if o["kind"] == "image")
    assert img["width"] == 1920 and not img["is_original"]  # preview image is never called "original"
    assert all("10.0.0.8" not in str(r.url) for r in web.seen)  # private candidate never fetched
    assert a["thumbnail_url"] == "https://blog.example/poster.jpg"


def test_page_without_media(client, web):
    web.on("blog.example", "/text", httpx.Response(200, content=b"<html><p>hi</p></html>",
                                                     headers={"content-type": "text/html"}))
    a = analyze(client, auth(client), "https://blog.example/text").json()
    assert a["status"] == "unavailable" and a["official_url"] == "https://blog.example/text"


def test_protected_platform_cdn_refused(client, web):
    web.file("rr5---sn-abc.googlevideo.com", "/videoplayback", MP4_HEAD, "video/mp4")
    a = analyze(client, auth(client), "https://rr5---sn-abc.googlevideo.com/videoplayback?expire=1").json()
    assert a["status"] == "unavailable" and "original post" in a["explanation"]
    assert not any(r.headers.get("host", "").endswith("googlevideo.com") for r in web.seen)


def test_rate_limiting(make_client, web):
    web.file("cdn.example", "/a.jpg", JPEG_HEAD, "image/jpeg")
    c = make_client(RATE_LIMIT_PER_MINUTE="3")
    h = auth(c)
    codes = [analyze(c, h, "https://cdn.example/a.jpg").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429
    r = analyze(c, h, "https://cdn.example/a.jpg")
    assert r.json()["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1


def test_history_opt_out_deletes_records(client, web):
    web.file("cdn.example", "/a.jpg", JPEG_HEAD, "image/jpeg")
    h = auth(client)
    assert client.patch("/api/v1/account/settings", json={"keep_server_history": False},
                        headers=h).json()["keep_server_history"] is False
    a = analyze(client, h, "https://cdn.example/a.jpg").json()
    did = client.post("/api/v1/downloads", json={"analysis_id": a["analysis_id"], "option_id": "f0"},
                      headers=h).json()["download"]["id"]
    client.patch(f"/api/v1/downloads/{did}", json={"status": "completed"}, headers=h)
    assert client.get(f"/api/v1/downloads/{did}", headers=h).status_code == 404


def test_register_login_logout_delete(client, web):
    h = auth(client)
    weak = client.post("/api/v1/auth/register", json={"email": "a@b.co", "password": "short"}, headers=h)
    assert weak.status_code == 422
    reg = client.post("/api/v1/auth/register", json={"email": "Ana@Example.com", "password": "correct horse battery"},
                      headers=h)
    assert reg.status_code == 201 and reg.json()["email"] == "ana@example.com" and not reg.json()["is_anonymous"]
    assert client.get("/api/v1/account", headers=h).status_code == 401  # old session rotated
    h = {"Authorization": f"Bearer {reg.json()['token']}"}
    other = auth(client)
    dup = client.post("/api/v1/auth/register", json={"email": "ana@example.com", "password": "another long pass"},
                      headers=other)
    assert dup.status_code == 409
    assert client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "wrong password!"}
                       ).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong password!"}
                       ).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "correct horse battery"})
    h2 = {"Authorization": f"Bearer {login.json()['token']}"}
    assert client.post("/api/v1/auth/logout", headers=h2).status_code == 204
    assert client.get("/api/v1/account", headers=h2).status_code == 401
    assert client.delete("/api/v1/account", headers=h).status_code == 204
    assert client.get("/api/v1/account", headers=h).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "correct horse battery"}
                       ).status_code == 401


def test_invalid_requests(client):
    h = auth(client)
    assert client.post("/api/v1/media/analyze", json={"url": ""}, headers=h).status_code == 422
    assert client.post("/api/v1/media/analyze", json={"nope": 1}, headers=h).status_code == 422
    assert client.post("/api/v1/downloads", json={"analysis_id": "x", "option_id": "f0"}, headers=h).status_code == 422
    big = client.post("/api/v1/media/analyze", content=b"{" + b" " * 70_000 + b"}", headers={
        **h, "content-type": "application/json"})
    assert big.status_code == 413
    r = client.post("/api/v1/media/analyze", json={"url": "https://www.youtube.com/@somechannel"}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "unsupported_link"


def test_retention_purge(client, web):
    import asyncio

    from app.config import get_settings
    from app.db import sessionmaker
    from app.models import Download, MediaAnalysis
    from app.services import purge_expired

    web.file("cdn.example", "/a.jpg", JPEG_HEAD, "image/jpeg")
    h = auth(client)
    a = analyze(client, h, "https://cdn.example/a.jpg").json()
    did = client.post("/api/v1/downloads", json={"analysis_id": a["analysis_id"], "option_id": "f0"},
                      headers=h).json()["download"]["id"]

    async def age_and_purge():
        async with sessionmaker()() as db:
            row = await db.get(Download, did)
            row.created_at = datetime.now(UTC) - timedelta(days=400)
            an = await db.get(MediaAnalysis, a["analysis_id"])
            an.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()
            await purge_expired(db, get_settings())
            return await db.get(Download, did), await db.get(MediaAnalysis, a["analysis_id"])

    d, an = client.portal.call(age_and_purge) if hasattr(client, "portal") and client.portal else asyncio.run(age_and_purge())
    assert d is None and an is None


def test_redirect_to_protected_cdn_is_refused(client, web):
    """Review finding: a short link redirecting to a platform CDN must not slip past the CDN block."""
    web.on("short.example", "/x", httpx.Response(302, headers={"location": "https://rr1---sn-x.googlevideo.com/videoplayback"}))
    web.file("rr1---sn-x.googlevideo.com", "/videoplayback", MP4_HEAD, "video/mp4")
    a = analyze(client, auth(client), "https://short.example/x").json()
    assert a["status"] == "unavailable" and a["analysis_id"] is None
    assert not any(r.headers.get("host", "").endswith("googlevideo.com") for r in web.seen)


def test_page_candidate_redirecting_to_protected_cdn_is_skipped(client, web):
    page = b'<meta property="og:video" content="https://media.example/go">'
    web.on("blog.example", "/p", httpx.Response(200, content=page, headers={"content-type": "text/html"}))
    web.on("media.example", "/go", httpx.Response(302, headers={"location": "https://v16.tiktokcdn.com/v.mp4"}))
    web.file("v16.tiktokcdn.com", "/v.mp4", MP4_HEAD, "video/mp4")
    a = analyze(client, auth(client), "https://blog.example/p").json()
    assert a["status"] == "unavailable" and a["options"] == []
