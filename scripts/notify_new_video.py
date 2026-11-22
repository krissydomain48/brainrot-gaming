"""Email Kit subscribers when a new (non-Short) video appears in data/videos.json.

Runs after scripts/sync_youtube.py in the GitHub Action. Needs the repo secret
KIT_API_KEY (a Kit V4 API key). Without it, the script only records which video
is newest, so switching emails on later never re-announces old uploads.

    python scripts/notify_new_video.py          # normal run
    KIT_TEST=1 python scripts/notify_new_video.py   # create a DRAFT in Kit only (nobody is emailed)

data/notified.json remembers every video already announced.
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
VIDEOS = os.path.join(ROOT, "data", "videos.json")
NOTIFIED = os.path.join(ROOT, "data", "notified.json")
SITE = "https://brainrot-gaming.com"
KIT_URL = "https://api.kit.com/v4/broadcasts"


def load(path, default):
    try:
        with open(path, encoding="utf8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, data):
    with open(path, "w", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def email_html(video):
    vid = html.escape(video["id"])
    title = html.escape(video["title"])
    watch = f"https://www.youtube.com/watch?v={vid}"
    thumb = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
    return f"""
<p>Hey crew 👋</p>
<p>A new video just dropped and you're hearing it first:</p>
<p><a href="{watch}"><img src="{thumb}" alt="{title}" width="560" style="max-width:100%;border-radius:12px;"></a></p>
<h2 style="margin:12px 0;">{title}</h2>
<p><a href="{watch}" style="display:inline-block;background:#ff5a36;color:#111;font-weight:bold;padding:12px 22px;border-radius:10px;text-decoration:none;">▶ Watch it now</a></p>
<p>Got something going on and want an honest opinion — or a story the crew needs to hear?
Send it to <a href="{SITE}/#ask">Ask Krissy</a>. I read every message, and some end up on Krissy Talks.</p>
<p>See you in the comments,<br>Krissy &amp; the crew</p>
<p style="font-size:12px;color:#888;">You're getting this because you joined the crew at brainrot-gaming.com.
<a href="{{{{ unsubscribe_url }}}}">Unsubscribe</a></p>
""".strip()


def kit_post(api_key, body):
    req = urllib.request.Request(
        KIT_URL,
        data=json.dumps(body).encode("utf8"),
        method="POST",
        headers={"X-Kit-Api-Key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, res.read().decode("utf8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf8", "replace")


def send(api_key, video, test):
    now = dt.datetime.now(dt.timezone.utc)
    body = {
        "subject": f"🎬 New video: {video['title']}"[:150],
        "preview_text": "It's up — come watch before everyone else does.",
        "description": f"Auto new-video email for {video['id']}" + (" (TEST DRAFT)" if test else ""),
        "content": email_html(video),
        "public": False,
        "published_at": iso(now),
        # A few minutes ahead so Kit treats it as a scheduled send; None = draft only.
        "send_at": None if test else iso(now + dt.timedelta(minutes=5)),
        "thumbnail_url": f"https://img.youtube.com/vi/{video['id']}/hqdefault.jpg",
        "thumbnail_alt": video["title"][:200],
    }
    status, text = kit_post(api_key, body)
    if status == 422 and "filter" in text.lower():
        # Kit's schema lists subscriber_filter as required; an empty group means everyone.
        body["subscriber_filter"] = [{"all": None, "any": None, "none": None}]
        status, text = kit_post(api_key, body)
    print(f"Kit responded {status}: {text[:500]}")
    return 200 <= status < 300


def main():
    data = load(VIDEOS, {})
    latest = (data.get("latest") or [None])[0]
    if not latest:
        print("No videos in data/videos.json")
        return 0

    state = load(NOTIFIED, None)
    api_key = os.environ.get("KIT_API_KEY", "").strip()
    test = os.environ.get("KIT_TEST", "").strip() in ("1", "true", "yes")

    if test:
        if not api_key:
            print("KIT_TEST needs the KIT_API_KEY secret")
            return 1
        ok = send(api_key, latest, test=True)
        print("Test draft created in Kit — check Send → Broadcasts. Nobody was emailed." if ok else "Test failed (see Kit response above).")
        return 0 if ok else 1

    if state is None:
        # First run: remember the current newest video without announcing it.
        save(NOTIFIED, {"sent": [latest["id"]]})
        print("Initialised data/notified.json with", latest["id"])
        return 0

    sent = state.get("sent", [])
    if latest["id"] in sent:
        print("Newest video already handled:", latest["id"])
        return 0

    if not api_key:
        print("New video", latest["id"], "but KIT_API_KEY is not set — recording it without emailing.")
    elif not send(api_key, latest, test=False):
        print("Email failed; will try again next run.")
        return 0  # don't record it, so the next run retries

    state["sent"] = (sent + [latest["id"]])[-200:]
    save(NOTIFIED, state)
    print("Recorded", latest["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
