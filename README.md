# UniversalStream — Multi-Host Stream API & Auto-Play Player Server

A high-performance Flask & Gunicorn API server and Glassmorphism Web Player that unifies stream extraction, decryption, and proxying across all major file hosting providers:

- **MixDrop** (`MDCore.wurl` packed extraction + MP4 proxy)
- **Streamta / Streamtape** (`/get_video` redirect resolution + MP4 proxy)
- **StreamWish / Playnixes** (HLS2 master playlist extraction + TS segment proxy)
- **Luluvdoo / Lulustream** (Session-based HLS playlist extraction)
- **Bysejikuar / Bikebyse** (AES-GCM encrypted playback decryption + HLS proxy)
- **Playmogo / DoodStream** (`pass_md5` token extraction + MP4 proxy)
- **Direct MP4 / M3U8 URLs**

---

## Key Features

1. **Multi-Host Auto-Failover**: Given a TMDB ID, IMDb ID, or serial, the server inspects all available `host-1`, `host-2`, `host-3`, ... links in `database.json` and automatically falls back to secondary hosts if a stream is deleted or unreachable.
2. **Interactive Host Switcher**: The Web Player displays all detected hosts for a movie/episode (`[MIXDROP]`, `[STREAMWISH]`, `[STREAMTAPE]`, `[DOODSTREAM]`, `[BYSEJIKUAR]`), allowing users to switch sources with a single click.
3. **Adaptive Video Player**: Built-in HTML5 Video and embedded **HLS.js** player with keyboard shortcuts, fullscreen, and mobile support.
4. **Fast Proxy Pipeline**: Handles Range headers (`206 Partial Content`), CORS headers, and HLS manifest rewriting so IP-bound CDN streams play flawlessly.

---

## Deploy to Render

### Option 1: Render Blueprint (`render.yaml`)
1. Push this repository to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com), click **New +** > **Blueprint**.
3. Connect `universalstream`. Render will automatically configure Python 3.11, Gunicorn, environment variables, and the health check (`/healthz`).

### Option 2: Render Web Service (Manual)
1. In Render Dashboard, click **New +** > **Web Service**.
2. Connect your repository.
3. Configure settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
   - **Health Check Path**: `/healthz`
4. Add Environment Variables (optional overrides):
   - `PROXY`: `http://zmglmvwl:puz74ldkgj3f@31.59.20.176:6754`
   - `DB_URL`: `https://raw.githubusercontent.com/ytbro8326-sudo/primesrc_single_flaresolver/refs/heads/main/custom_merged_data.json`
   - `DB_REFRESH_SECS`: `3600`

---

## Docker Deployment

```bash
docker-compose up -d --build
```

---

## API Endpoints

| Method | Path | Response | Description |
|--------|------|----------|-------------|
| `GET`  | `/` | HTML / JSON | Web player & interactive search explorer |
| `GET`  | `/healthz` | JSON | Service health check |
| `GET`  | `/api/<int:tmdb_id>` | HTML / JSON | Multi-host extraction & player by TMDB ID (e.g. `/api/68`) |
| `GET`  | `/api/<imdb_id>` | HTML / JSON | Multi-host extraction & player by IMDb ID (e.g. `/api/tt0088846`) |
| `GET`  | `/api/direct/<url>` | HTML / JSON | Direct provider URL extraction (e.g. `/api/direct/https://mixdrop.ag/e/...`) |
| `POST` | `/api/extract` | JSON | JSON endpoint: `{"url": "..."}` |
| `GET`  | `/api/db/stats` | JSON | Total entries and database metadata |
| `GET`  | `/api/db/search?q=<query>` | JSON | Search database by title, TMDB, or IMDb |
| `GET`  | `/stream/<video_id>` | MP4 Stream | Proxied IP-bound MP4 video stream (supports Range) |
| `GET`  | `/proxy?url=<target_url>` | HLS / TS Stream | Proxied HLS playlist & TS video segments |
