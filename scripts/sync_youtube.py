"""Pull the channel's latest uploads and vlogs into data/videos.json.

Reads YouTube's public playlist pages (no API key needed). Run by
.github/workflows/sync-youtube.yml every few hours; safe to run by hand:

    python scripts/sync_youtube.py

If YouTube returns nothing usable, the existing data/videos.json is left
untouched so the site never goes blank.
"""
import json
import os
import re
import sys
import urllib.request

CHANNEL_ID = "UC0brnbM_0wJjJ3ARH8cuEYw"
UPLOADS_PLAYLIST = "UU" + CHANNEL_ID[2:]
# Playlists whose videos count as vlogs.
VLOG_PLAYLISTS = ["PLKE8nRFo6L1M", "PLOAIUeT_hy4gadtEATXRK-LMtJQ9yhjHb"]  # Travel Vlogs, Videography
# Uploads whose title matches this also count as vlogs.
VLOG_TITLE = re.compile(r"\bvlog|krissy talks|day trip|village life", re.I)

LATEST_COUNT = 6
SHORTS_COUNT = 6
VLOG_COUNT = 6
SHORT_MAX_SECONDS = 180

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "videos.json")


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36",
        "Accept-Language": "en",
        "Cookie": "SOCS=CAI",  # skip the EU cookie-consent interstitial
    })
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf8")


def walk(node, key):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                yield v
            yield from walk(v, key)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v, key)


def playlist_videos(playlist_id):
    html = fetch("https://www.youtube.com/playlist?list=" + playlist_id)
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    found = []  # (videoId, title, seconds)

    # Older page layout
    for r in walk(data, "playlistVideoRenderer"):
        if not r.get("videoId") or not r.get("isPlayable", True):
            continue
        title = "".join(run.get("text", "") for run in r.get("title", {}).get("runs", []))
        found.append((r["videoId"], title, int(r.get("lengthSeconds") or 0)))

    # Newer page layout (lockupViewModel)
    for r in walk(data, "lockupViewModel"):
        if r.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO" or not r.get("contentId"):
            continue
        try:
            title = r["metadata"]["lockupMetadataViewModel"]["title"]["content"]
        except (KeyError, TypeError):
            continue
        badge = next(walk(r.get("contentImage", {}), "thumbnailBadgeViewModel"), {})
        found.append((r["contentId"], title, duration_seconds(badge.get("text", ""))))

    videos, seen = [], set()
    for vid, title, seconds in found:
        if vid in seen:
            continue
        seen.add(vid)
        is_short = "#shorts" in title.lower() or (0 < seconds <= SHORT_MAX_SECONDS)
        videos.append({"id": vid, "title": title.strip(), "short": is_short})
    return videos


def duration_seconds(text):
    """'1:06' -> 66, '1:02:03' -> 3723, anything else -> 0."""
    if not re.fullmatch(r"\d+(:\d{2}){1,2}", text or ""):
        return 0
    total = 0
    for part in text.split(":"):
        total = total * 60 + int(part)
    return total


def main():
    try:
        uploads = playlist_videos(UPLOADS_PLAYLIST)
    except Exception as exc:  # network / layout change
        print("Could not read uploads:", exc)
        return 0
    if not uploads:
        print("No uploads parsed; keeping existing data/videos.json")
        return 0

    latest = [v for v in uploads if not v["short"]][:LATEST_COUNT]
    shorts = [v for v in uploads if v["short"]][:SHORTS_COUNT]

    vlogs, seen = [], set()
    candidates = [v for v in uploads if not v["short"] and VLOG_TITLE.search(v["title"])]
    for pid in VLOG_PLAYLISTS:
        try:
            candidates += [v for v in playlist_videos(pid) if not v["short"]]
        except Exception as exc:
            print("Could not read playlist", pid, exc)
    upload_order = {v["id"]: i for i, v in enumerate(uploads)}
    candidates.sort(key=lambda v: upload_order.get(v["id"], 10**6))
    for v in candidates:
        if v["id"] not in seen:
            seen.add(v["id"])
            vlogs.append(v)
    vlogs = vlogs[:VLOG_COUNT]

    strip = lambda vs: [{"id": v["id"], "title": v["title"]} for v in vs]
    new = {"latest": strip(latest), "shorts": strip(shorts), "vlogs": strip(vlogs)}

    try:
        with open(OUT, encoding="utf8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = None
    if old and {k: old.get(k) for k in new} == new:
        print("No changes")
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf8") as f:
        json.dump(new, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Updated: {len(latest)} latest, {len(shorts)} shorts, {len(vlogs)} vlogs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
