# brainrot-gaming
Official website for Brainrot Krissy — a Brisbane-based entertainment channel made with friends: vlogs, Krissy Talks podcasts and talk shows, challenges, and some gaming chaos.

## How the site updates

- **Videos, Shorts and Vlogs** load from `data/videos.json`. The GitHub Action
  `.github/workflows/sync-youtube.yml` refreshes that file from the YouTube channel
  every 2 hours and rebuilds the site. To update right away: GitHub → Actions →
  "Sync YouTube videos" → Run workflow.
- **Vlogs** = the "Travel Vlogs" and "Videography" playlists, plus any upload with
  "vlog" or "Krissy Talks" in the title (see `VLOG_PLAYLISTS` / `VLOG_TITLE` in
  `scripts/sync_youtube.py`).
- **Merch** is the `MERCH` list near the top of the script in `index.html`
  (RotGoblinDesigns on Etsy). Add or remove items there.
