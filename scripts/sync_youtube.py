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
    found = []  # (videoId, title, seconds, views, age_days)

    # Older page layout
    for r in walk(data, "playlistVideoRenderer"):
        if not r.get("videoId") or not r.get("isPlayable", True):
            continue
        title = "".join(run.get("text", "") for run in r.get("title", {}).get("runs", []))
        labels = [run.get("text", "") for run in r.get("videoInfo", {}).get("runs", [])]
        found.append((r["videoId"], title, int(r.get("lengthSeconds") or 0),
                      parse_views(labels), parse_age_days(labels)))

    # Newer page layout (lockupViewModel)
    for r in walk(data, "lockupViewModel"):
        if r.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO" or not r.get("contentId"):
            continue
        try:
            meta = r["metadata"]["lockupMetadataViewModel"]
            title = meta["title"]["content"]
        except (KeyError, TypeError):
            continue
        badge = next(walk(r.get("contentImage", {}), "thumbnailBadgeViewModel"), {})
        labels = [p.get("accessibilityLabel", "") for p in walk(meta.get("metadata", {}), "metadataParts") for p in p]
        found.append((r["contentId"], title, duration_seconds(badge.get("text", "")),
                      parse_views(labels), parse_age_days(labels)))

    videos, seen = [], set()
    for vid, title, seconds, views, age in found:
        if vid in seen:
            continue
        seen.add(vid)
        is_short = "#shorts" in title.lower() or (0 < seconds <= SHORT_MAX_SECONDS)
        videos.append({"id": vid, "title": title.strip(), "short": is_short,
                       "views": views, "age_days": age})
    return videos


VIEW_SCALE = {"": 1, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}


def parse_views(labels):
    """'1,234 views' -> 1234, '1.2 thousand views' -> 1200; None if not shown."""
    for text in labels:
        m = re.search(r"([\d,.]+)\s*(thousand|million|billion)?\s+views?\b", text or "", re.I)
        if m:
            return int(float(m.group(1).replace(",", "")) * VIEW_SCALE[(m.group(2) or "").lower()])
    return None


AGE_UNITS = {"minute": 1 / 1440, "hour": 1 / 24, "day": 1, "week": 7, "month": 30, "year": 365}


def parse_age_days(labels):
    """['21 hours ago'] -> 0.875; None if no age is shown."""
    for text in labels:
        m = re.search(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", text or "")
        if m:
            return int(m.group(1)) * AGE_UNITS[m.group(2)]
    return None


def number_from(text):
    """'192,088 views' -> 192088."""
    m = re.search(r"[\d,]+", text or "")
    return int(m.group(0).replace(",", "")) if m else None


def channel_stats():
    html = fetch(f"https://www.youtube.com/channel/{CHANNEL_ID}/about")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    if not m:
        return None
    about = next(walk(json.loads(m.group(1)), "aboutChannelViewModel"), None)
    if not about:
        return None
    subs = (about.get("subscriberCountText") or "").replace("subscribers", "").replace("subscriber", "").strip()
    joined = (about.get("joinedDateText") or {}).get("content", "")
    jm = re.search(r"Joined\s+([A-Za-z]+)\s+\d+,\s+(\d{4})", joined)
    return {
        "subscribers": subs or None,                       # e.g. "1.64K" (YouTube rounds this)
        "views": number_from(about.get("viewCountText")),  # exact total views
        "videos": number_from(about.get("videoCountText")),
        "joined": f"{jm.group(1)} {jm.group(2)}" if jm else None,
    }


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

    # Most-viewed regular video among the recent uploads listed on the page.
    ranked = [v for v in uploads if not v["short"] and v["views"] is not None]
    if ranked:
        top = max(ranked, key=lambda v: v["views"])
        new["top"] = {"id": top["id"], "title": top["title"], "views": top["views"]}

    try:
        stats = channel_stats()
    except Exception as exc:
        print("Could not read channel stats:", exc)
        stats = None
    try:
        with open(OUT, encoding="utf8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = None
    if stats:
        recent = [v for v in uploads if v["age_days"] is not None and v["age_days"] <= 28]
        stats["uploads_per_week"] = round(len(recent) / 4, 1)
        new["stats"] = stats
    elif old and old.get("stats"):
        new["stats"] = old["stats"]  # keep the last good numbers

    # Only rewrite (and so commit + rebuild the site) when something visible
    # changed. View counts tick up constantly, so compare them in thousands.
    def signature(d):
        if not d:
            return None
        sig = {k: d.get(k) for k in ("latest", "shorts", "vlogs")}
        s = dict(d.get("stats") or {})
        if s.get("views") is not None:
            s["views"] //= 1000
        sig["stats"] = s
        sig["top"] = (d.get("top") or {}).get("id")
        return sig

    if signature(old) == signature(new):
        print("No changes")
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf8") as f:
        json.dump(new, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Updated: {len(latest)} latest, {len(shorts)} shorts, {len(vlogs)} vlogs, "
          f"top={new.get('top', {}).get('id')}, stats={new.get('stats')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
