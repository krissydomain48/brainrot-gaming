"""Build the static Krissy Talks page (krissy-talks/index.html) and sitemap.xml.

Episodes = the "Krissy Talks" playlist + any regular upload whose title mentions
"Krissy Talks" or "Worst Life Advice". Each episode's description, date and
length are read once from its YouTube page and cached in data/episodes.json.
The page is plain HTML (no JavaScript needed to see episodes) so Google can
index every episode, with VideoObject structured data for video results.

    python scripts/build_krissy_talks.py

If YouTube can't be read, the existing page is left as it is.
"""
import datetime as dt
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sync_youtube as yt  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
CACHE = os.path.join(ROOT, "data", "episodes.json")
PAGE = os.path.join(ROOT, "krissy-talks", "index.html")
SITEMAP = os.path.join(ROOT, "sitemap.xml")
SITE = "https://brainrot-gaming.com"
PLAYLIST = "PLFXckBsX_JtM"
TITLE_MATCH = re.compile(r"krissy\s*talks|worst\s+life\s+advice", re.I)


def load_cache():
    try:
        with open(CACHE, encoding="utf8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def video_details(video_id):
    page = yt.fetch("https://www.youtube.com/watch?v=" + video_id)
    m = re.search(r"var ytInitialPlayerResponse = (\{.*?\});(?:var|</script>)", page, re.S)
    if not m:
        return None
    data = json.loads(m.group(1))
    vd = data.get("videoDetails", {})
    mf = data.get("microformat", {}).get("playerMicroformatRenderer", {})
    return {
        "title": (vd.get("title") or "").strip(),
        "description": vd.get("shortDescription") or "",
        "seconds": int(vd.get("lengthSeconds") or 0),
        "published": mf.get("publishDate") or mf.get("uploadDate") or "",
    }


def blurb(description, limit=520):
    """First readable paragraphs of a YouTube description, without links/hashtags."""
    keep = []
    for line in description.splitlines():
        line = line.strip()
        if not line or "http" in line or line.startswith("#") or line.startswith("👉"):
            continue
        if re.fullmatch(r"(#\w+\s*)+", line):
            continue
        keep.append(line)
    text = " ".join(keep)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[: end + 1] if end > limit * 0.5 else cut.rsplit(" ", 1)[0] + "…").strip()


def iso_duration(seconds):
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return "PT" + (f"{h}H" if h else "") + (f"{m}M" if m else "") + f"{s}S"


def nice_length(seconds):
    m = round(seconds / 60)
    return f"{m // 60} hr {m % 60} min" if m >= 60 else f"{m} min"


def nice_date(published):
    try:
        return dt.date.fromisoformat(published[:10]).strftime("%-d %B %Y") if os.name != "nt" else \
            dt.date.fromisoformat(published[:10]).strftime("%#d %B %Y")
    except ValueError:
        return ""


def gather():
    found = {}
    for v in yt.playlist_videos(PLAYLIST):
        if not v["short"]:
            found[v["id"]] = v["title"]
    for v in yt.playlist_videos(yt.UPLOADS_PLAYLIST):
        if not v["short"] and TITLE_MATCH.search(v["title"]):
            found.setdefault(v["id"], v["title"])
    return found


def render(episodes):
    e = html.escape
    cards, items = [], []
    for i, ep in enumerate(episodes, 1):
        vid = e(ep["id"])
        thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        cards.append(f"""
      <article class="episode" id="ep-{vid}">
        <a class="thumb" href="https://www.youtube.com/watch?v={vid}" target="_blank" rel="noopener" data-video="{vid}">
          <img src="{thumb}" alt="{e(ep['title'])}" loading="lazy" width="480" height="360">
          <span class="play">▶</span>
        </a>
        <div class="info">
          <p class="meta">{e(nice_date(ep['published']))} · {e(nice_length(ep['seconds']))}</p>
          <h2>{e(ep['title'])}</h2>
          <p>{e(blurb(ep['description']))}</p>
          <a class="btn btn-primary" href="https://www.youtube.com/watch?v={vid}" target="_blank" rel="noopener">Watch on YouTube</a>
        </div>
      </article>""")
        items.append({
            "@type": "ListItem",
            "position": i,
            "item": {
                "@type": "VideoObject",
                "name": ep["title"],
                "description": blurb(ep["description"], 300) or ep["title"],
                "thumbnailUrl": [thumb],
                "uploadDate": ep["published"],
                "duration": iso_duration(ep["seconds"]),
                "embedUrl": f"https://www.youtube.com/embed/{ep['id']}",
                "contentUrl": f"https://www.youtube.com/watch?v={ep['id']}",
            },
        })
    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Krissy Talks episodes",
        "itemListElement": items,
    }, ensure_ascii=False, indent=2).replace("</", "<\\/")
    count = len(episodes)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Krissy Talks — Worst Life Advice &amp; Real Talk Podcast | Brainrot Krissy</title>
  <meta name="description" content="Krissy Talks is the podcast where Krissy and his brother Roshan give the worst life advice on the internet, tell Nepali village stories and talk real life from Brisbane. Watch all {count} episodes." />
  <link rel="canonical" href="{SITE}/krissy-talks/" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="Krissy Talks — Worst Life Advice &amp; Real Talk Podcast" />
  <meta property="og:description" content="Two brothers, the worst life advice on the internet, and real talk. Watch every Krissy Talks episode." />
  <meta property="og:url" content="{SITE}/krissy-talks/" />
  <meta property="og:image" content="{SITE}/og-image.jpg" />
  <meta name="twitter:card" content="summary_large_image" />
  <link rel="icon" type="image/png" href="/logo.png" />
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-MQBRN37M8Y"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-MQBRN37M8Y');</script>
  <script type="application/ld+json">
{schema}
  </script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: Arial, Helvetica, sans-serif; background: #08090d; color: #fff; line-height: 1.6; }}
    a {{ color: inherit; text-decoration: none; }}
    img {{ max-width: 100%; display: block; }}
    .container {{ width: min(1050px, 92%); margin: auto; }}
    .navbar {{ position: sticky; top: 0; z-index: 10; background: rgba(8,9,13,.95); border-bottom: 1px solid rgba(255,183,3,.3); }}
    .nav-inner {{ display: flex; justify-content: space-between; align-items: center; padding: 14px 0; gap: 16px; flex-wrap: wrap; }}
    .brand {{ display: flex; align-items: center; gap: 12px; font-weight: 800; color: #ffb703; }}
    .brand img {{ width: 44px; height: 44px; border-radius: 12px; }}
    .nav-links {{ display: flex; gap: 18px; flex-wrap: wrap; font-weight: 600; color: #e9e9e9; }}
    .nav-links a:hover {{ color: #ffb703; }}
    .hero {{ padding: 64px 0 36px; }}
    .tag {{ display: inline-block; padding: 7px 13px; border-radius: 999px; background: rgba(255,90,54,.14); border: 1px solid rgba(255,140,102,.35); color: #ff8f70; font-weight: 700; font-size: .9rem; margin-bottom: 16px; }}
    h1 {{ font-size: clamp(2.2rem, 6vw, 3.8rem); line-height: 1.05; margin-bottom: 16px; }}
    h1 span {{ color: #ffb703; }}
    .lead {{ font-size: 1.08rem; color: #e1e1e1; max-width: 720px; }}
    .btn {{ display: inline-block; padding: 12px 20px; border-radius: 12px; font-weight: 800; }}
    .btn-primary {{ background: linear-gradient(135deg, #ff5a36, #ffb703); color: #111; }}
    .btn-secondary {{ background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.15); }}
    .buttons {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 24px; }}
    .episodes {{ display: grid; gap: 22px; padding: 20px 0 50px; }}
    .episode {{ display: grid; grid-template-columns: 360px 1fr; gap: 22px; padding: 18px; border-radius: 20px; background: linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.025)); border: 1px solid rgba(255,255,255,.08); }}
    .thumb {{ position: relative; border-radius: 14px; overflow: hidden; aspect-ratio: 16/9; background: #000; }}
    .thumb img, .thumb iframe {{ width: 100%; height: 100%; object-fit: cover; border: 0; }}
    .play {{ position: absolute; inset: 0; display: grid; place-items: center; font-size: 2.4rem; color: #fff; text-shadow: 0 4px 20px rgba(0,0,0,.6); }}
    .meta {{ color: #ffb703; font-weight: 700; font-size: .9rem; }}
    .episode h2 {{ font-size: 1.3rem; margin: 6px 0 10px; }}
    .episode p {{ color: #d6d6d6; margin-bottom: 14px; }}
    .box {{ padding: 26px; border-radius: 20px; background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); margin-bottom: 26px; }}
    .box h2 {{ color: #ffb703; margin-bottom: 10px; }}
    .box p {{ color: #d6d6d6; margin-bottom: 10px; }}
    footer {{ border-top: 1px solid rgba(255,255,255,.08); padding: 26px 0; text-align: center; color: #bbb; font-size: .95rem; }}
    @media (max-width: 760px) {{ .episode {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <nav class="navbar">
    <div class="container nav-inner">
      <a href="/" class="brand"><img src="/logo.png" alt="Brainrot Krissy logo" width="44" height="44"><span>BRAINROT KRISSY</span></a>
      <div class="nav-links">
        <a href="/">Home</a>
        <a href="/#latest-videos">Videos</a>
        <a href="/#vlogs">Vlogs</a>
        <a href="/#merch">Merch</a>
        <a href="/#ask">Ask Krissy</a>
      </div>
    </div>
  </nav>

  <main class="container">
    <header class="hero">
      <div class="tag">THE PODCAST</div>
      <h1>Krissy <span>Talks</span></h1>
      <p class="lead">Two brothers, zero qualifications, and the worst life advice on the internet. Krissy and Roshan pull real problems out of a jar, argue about music, tell Nepali village stories and talk about growing up between Nepal and Brisbane — {count} episode{'s' if count != 1 else ''} so far.</p>
      <div class="buttons">
        <a class="btn btn-primary" href="https://www.youtube.com/playlist?list={PLAYLIST}" target="_blank" rel="noopener">Watch the playlist</a>
        <a class="btn btn-secondary" href="/#ask">Send your problem to Ask Krissy</a>
      </div>
    </header>

    <section class="episodes" aria-label="Episodes">{''.join(cards)}
    </section>

    <section class="box">
      <h2>What is Krissy Talks?</h2>
      <p>Krissy Talks is a comedy podcast from the Brainrot Krissy channel. In the <strong>Worst Life Advice</strong> episodes, viewers' real problems get the most questionable answers possible — please don't actually follow any of it. Other episodes are just two brothers talking: country music versus Justin Bieber, buffalo boys instead of cowboys, and what life in a Nepali village taught us.</p>
      <p>Got a problem you want the worst possible advice on — or a real story you want heard? Send it through <a href="/#ask" style="color:#ffb703;font-weight:700;">Ask Krissy</a>. You choose if it's shared and whether your name is used.</p>
    </section>

    <section class="box">
      <h2>Never miss an episode</h2>
      <p>Join the crew and get an email the moment a new episode drops.</p>
      <div class="buttons"><a class="btn btn-primary" href="/#join">Join the Crew</a>
      <a class="btn btn-secondary" href="https://youtube.com/@brainrotgaming61?sub_confirmation=1" target="_blank" rel="noopener">Subscribe on YouTube</a></div>
    </section>
  </main>

  <footer><div class="container"><p>© 2026 Brainrot Krissy · <a href="/">brainrot-gaming.com</a></p></div></footer>

  <script>
    // Click a thumbnail to play the episode right here instead of leaving the page.
    document.querySelectorAll('.thumb[data-video]').forEach(function (a) {{
      a.addEventListener('click', function (ev) {{
        ev.preventDefault();
        var id = a.getAttribute('data-video');
        a.innerHTML = '<iframe src="https://www.youtube.com/embed/' + id + '?autoplay=1" title="Krissy Talks episode" allow="autoplay; encrypted-media; picture-in-picture; web-share" allowfullscreen></iframe>';
        if (typeof gtag === 'function') gtag('event', 'play_episode', {{ event_category: 'krissy_talks', event_label: id }});
      }}, {{ once: true }});
    }});
  </script>
</body>
</html>
"""


def write_if_changed(path, text):
    try:
        with open(path, encoding="utf8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf8", newline="\n") as f:
        f.write(text)
    return True


def sitemap(latest):
    lastmod = (latest or dt.date.today().isoformat())[:10]
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{SITE}/</loc>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{SITE}/krissy-talks/</loc>
    <lastmod>{lastmod}</lastmod>
    <priority>0.9</priority>
  </url>
</urlset>
"""


def main():
    try:
        found = gather()
    except Exception as exc:
        print("Could not read YouTube:", exc)
        return 0
    if not found:
        print("No Krissy Talks episodes found; leaving the page as it is")
        return 0

    cache = load_cache()
    for vid in found:
        if vid in cache:
            continue
        try:
            info = video_details(vid)
        except Exception as exc:
            print("Could not read", vid, exc)
            info = None
        if info:
            cache[vid] = info
    episodes = [dict(cache[v], id=v) for v in found if v in cache]
    episodes.sort(key=lambda ep: ep["published"], reverse=True)

    changed = write_if_changed(CACHE, json.dumps(cache, ensure_ascii=False, indent=2) + "\n")
    changed |= write_if_changed(PAGE, render(episodes))
    changed |= write_if_changed(SITEMAP, sitemap(episodes[0]["published"] if episodes else None))
    print(f"{len(episodes)} episodes; {'updated' if changed else 'no changes'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
