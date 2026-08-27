"""
Universal Stream Player & Multi-Host API Server

Unified extraction, proxying, and auto-play player supporting:
- MixDrop (MP4)
- Streamta / Streamtape (MP4)
- StreamWish / Playnixes (HLS / M3U8)
- Luluvdoo / Lulustream (HLS / M3U8)
- Bysejikuar / Bikebyse (AES-GCM HLS)
- Playmogo / DoodStream (MP4)
- Generic Direct Streams (MP4 / M3U8)
"""

from __future__ import annotations

import ast
import base64
import json
import logging
import os
import random
import re
import string
import sys
import threading
import time
from typing import Optional, Tuple, Any, Dict, List
from urllib.parse import urljoin, urlparse, quote, unquote, urlunparse

import requests
from flask import Flask, Response, jsonify, request, stream_with_context
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    import cloudscraper
except Exception:
    cloudscraper = None

# ---------------------------------------------------------------------------
# Config & Defaults
# ---------------------------------------------------------------------------

DEFAULT_PROXY = os.getenv("PROXY", "http://zmglmvwl:puz74ldkgj3f@31.59.20.176:6754")
PROXIES_POOL = [
    DEFAULT_PROXY,
    "http://zmglmvwl:puz74ldkgj3f@45.38.107.97:6014",
    "http://zmglmvwl:puz74ldkgj3f@198.105.121.200:6462",
    "http://zmglmvwl:puz74ldkgj3f@64.137.96.74:6641",
    "http://zmglmvwl:puz74ldkgj3f@198.23.243.226:6361",
    "http://zmglmvwl:puz74ldkgj3f@38.154.185.97:6370",
    "http://zmglmvwl:puz74ldkgj3f@84.247.60.125:6095",
    "http://zmglmvwl:puz74ldkgj3f@142.111.67.146:5611",
    "http://zmglmvwl:puz74ldkgj3f@191.96.254.138:6185",
    "http://zmglmvwl:puz74ldkgj3f@31.58.9.4:6077",
]

DB_URL = os.getenv(
    "DB_URL",
    "https://raw.githubusercontent.com/ytbro8326-sudo/primesrc_single_flaresolver/refs/heads/main/custom_merged_data.json"
)
GITHUB_TOKEN = (os.getenv("GITHUB_TOKEN") or "").strip()
DB_REFRESH_SECS = int(os.getenv("DB_REFRESH_SECS", "3600"))

# Provider Aliases
MIXDROP_ALIASES = {
    "mixdrop.ag", "mixdrop.co", "mixdrop.to", "mixdrop.sx", "mixdrop.bz",
    "mixdrop.ch", "mixdrop.is", "mixdrop.vc", "mixdrop.club", "mixdrop.si",
    "miiixdrop.net", "mixdrop.nu", "mixdrop.vip", "mixdrop.ps", "mixdrop.cat",
    "mixdrop.click", "mixdrop.space", "miixdrop.top",
}

STREAMTA_ALIASES = {
    "streamta.site", "streamtape.com", "streamtape.net", "streamtape.to",
    "streamta.to", "streamta.com", "streamtape.xyz", "streamta.co",
}

STREAMWISH_ALIASES = {
    "streamwish.to", "streamwish.com", "playnixes.com", "swishsrv.com",
    "flaswish.com", "streamwish.site", "streamwish.xyz", "wishembed.pro",
    "embedwish.com", "awish.pro", "streamwish.org", "filelions.to",
}

LULUVDOO_ALIASES = {
    "luluvdoo.com", "luluvdo.com", "luluvid.com", "lulustream.com",
    "luluvstream.com", "luluvdo.net", "lulustream.to", "luluvdoo.to",
}

BYSE_ALIASES = {
    "bysejikuar.com", "bikebyse.com", "byse.com", "bysejikuar",
}

DOOD_ALIASES = {
    "dood.watch", "dood.so", "dood.li", "doods.pro",
    "vidply.com", "ds2play.com", "ds2video.com", "d-s.io",
    "d000d.com", "d0000d.com", "dood.ws", "dood.pm",
    "dood.re", "dood.to", "playmogo.com",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("universal-stream-api")

app = Flask(__name__)

_db: list = []
_db_lock = threading.Lock()
_db_fetched_at: float = 0.0
stream_cache: dict = {}

# ---------------------------------------------------------------------------
# JS Unpackers & Encryption Helpers
# ---------------------------------------------------------------------------

def unpack(p, a=None, c=None, k=None, e=None, d=None):
    """Deanpacker for packed JavaScript functions."""
    if a is None and c is None and k is None:
        # Auto-extract parameters from string
        pattern = r"\}\('(.*)',\s*(\d+),\s*(\d+),\s*'(.*)'\.split\('\|'\)"
        m = re.search(pattern, p, re.DOTALL)
        if not m:
            pattern2 = r'eval\(function\((.*?)\)\{.*?\}\((.*?)\)\)'
            m2 = re.search(pattern2, p, re.DOTALL)
            if not m2:
                return p
            raw = m2.group(2).replace(".split('|')", "")
            try:
                data = ast.literal_eval(raw)
                p, a, c, k = data[0], int(data[1]), int(data[2]), data[3].split('|')
            except Exception:
                return p
        else:
            p, a, c, k = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4).split("|")

    digits = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def base_encode(n):
        rem = n % a
        digit = digits[rem] if rem < len(digits) else str(rem)
        if n < a:
            return digit
        return base_encode(n // a) + digit

    d = {} if d is None else d
    for i in range(c - 1, -1, -1):
        key = base_encode(i)
        d[key] = k[i] if i < len(k) and k[i] else key

    def replace(match):
        w = match.group(0)
        return d.get(w, w)

    return re.sub(r"\b\w+\b", replace, p)


def decrypt_playback(playback: dict) -> dict:
    """Decrypt Bysejikuar AES-GCM encrypted playback payload."""
    try:
        data_b64 = playback.get("data")
        iv_b64 = playback.get("iv")
        key_b64 = playback.get("key")
        tag_b64 = playback.get("tag")

        if not all([data_b64, iv_b64, key_b64]):
            return {}

        ciphertext = base64.b64decode(data_b64)
        iv = base64.b64decode(iv_b64)
        key = base64.b64decode(key_b64)
        tag = base64.b64decode(tag_b64) if tag_b64 else b""

        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(iv, ciphertext + tag, None)
        return json.loads(decrypted.decode("utf-8"))
    except Exception as e:
        logger.error(f"AES-GCM decryption failed: {e}")
        return {}


def extract_signed_get_video_candidates(html: str) -> list[str]:
    """Extract Streamtape signed /get_video links."""
    seen = []
    def add(u: str):
        if not u:
            return
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = "https://streamta.site" + u
        if u not in seen:
            seen.append(u)

    m = re.search(r"document\.getElementById\(['\"](?:robotlink|videolink|streamtape|norobotlink)['\"]\)\.innerHTML\s*=\s*['\"]([^'\"]+)['\"]", html)
    if m:
        add(m.group(1))

    m2 = re.search(r"getElementById\('robotlink'\)\.innerHTML\s*=\s*(.*?);", html)
    if m2:
        parts = re.findall(r"['\"]([^'\"]+)['\"]", m2.group(1))
        if parts:
            add("".join(parts))

    for found in re.findall(r"['\"]((?:https?:)?//[^\s'\"]+/get_video\?[^\s'\"]+)['\"]", html):
        add(found)

    return seen


def _make_dood_play(token: str) -> str:
    """Generate Doodstream / Playmogo stream token path."""
    rnd = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
    return f"{rnd}?token={token}&expiry={int(time.time() * 1000)}"


# ---------------------------------------------------------------------------
# DB Helpers
# ---------------------------------------------------------------------------

def _fetch_db() -> list:
    token = (os.getenv("GITHUB_TOKEN") or "").strip() or GITHUB_TOKEN
    urls_to_try = [
        DB_URL,
        "https://raw.githubusercontent.com/ytbro8326-sudo/primesrc_single_flaresolver/refs/heads/main/custom_merged_data.json",
        "https://raw.githubusercontent.com/ytbro8326-sudo/primesrc_single_flaresolver/main/custom_merged_data.json",
        "https://api.github.com/repos/ytbro8326-sudo/primesrc_single_flaresolver/contents/custom_merged_data.json",
    ]

    for url in urls_to_try:
        # 1. Direct fetch
        try:
            headers = {
                "Accept": "application/vnd.github.v3.raw, application/json, text/plain, */*",
                "User-Agent": "Universal-Stream-API/1.0",
            }
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                logger.info(f"DB loaded successfully from remote GitHub: {len(data)} entries (via {url})")
                return data
        except Exception as err:
            logger.debug(f"Direct DB fetch {url} failed: {err}")

        # 2. Authenticated fetch if token present
        if token:
            for auth_prefix in ["Bearer", "token"]:
                try:
                    headers = {
                        "Accept": "application/vnd.github.v3.raw, application/json, text/plain, */*",
                        "User-Agent": "Universal-Stream-API/1.0",
                        "Authorization": f"{auth_prefix} {token}"
                    }
                    r = requests.get(url, headers=headers, timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        logger.info(f"DB loaded with token: {len(data)} entries (via {url})")
                        return data
                except Exception as err:
                    logger.debug(f"Auth DB fetch {url} ({auth_prefix}) failed: {err}")

    # Fallback to local bundled database.json
    for local_file in ["database.json", "custom_merged_data.json"]:
        if os.path.exists(local_file):
            try:
                with open(local_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info(f"DB loaded successfully from local file '{local_file}': {len(data)} entries")
                    return data
            except Exception as e:
                logger.warning(f"Failed to read local DB '{local_file}': {e}")

    logger.error("DB fetch failed: unable to fetch from remote repo and no local fallback found")
    return []


def get_db() -> list:
    global _db, _db_fetched_at
    now = time.time()
    with _db_lock:
        if not _db or (now - _db_fetched_at) > DB_REFRESH_SECS:
            _db = _fetch_db()
            _db_fetched_at = now
        return _db


def lookup_by_tmdb(tmdb_id: str) -> Optional[dict]:
    target = str(tmdb_id).strip()
    for entry in get_db():
        ti = str(entry.get("tmdb/imdb") or "").strip()
        parts = ti.split("/")
        if parts[0].strip() == target:
            return entry
    return None


def lookup_by_imdb(imdb_id: str) -> Optional[dict]:
    target = imdb_id.strip().lower()
    if not target.startswith("tt"):
        target = "tt" + target
    for entry in get_db():
        ti = str(entry.get("tmdb/imdb") or "").strip()
        parts = ti.split("/")
        if len(parts) > 1 and parts[1].strip().lower() == target:
            return entry
    return None


def lookup_any(query_id: str) -> Optional[dict]:
    """Matches by TMDB ID, IMDB ID, serial, or entry title."""
    q = str(query_id).strip()
    if not q:
        return None

    # Check TMDB exact match
    entry = lookup_by_tmdb(q)
    if entry:
        return entry

    # Check IMDB
    if q.lower().startswith("tt") or (q.isdigit() and len(q) >= 7):
        entry = lookup_by_imdb(q)
        if entry:
            return entry

    # Check serial
    if q.isdigit():
        q_int = int(q)
        for e in get_db():
            if e.get("serial") == q_int:
                return e

    # Check title substring
    q_low = q.lower()
    for e in get_db():
        t = str(e.get("title") or "").lower()
        if q_low == t:
            return e

    return None


def search_db(query: str, limit: int = 20) -> list[dict]:
    """Search DB by title, TMDB ID, or IMDb ID."""
    q = query.strip().lower()
    if not q:
        return []
    results = []
    for e in get_db():
        title = str(e.get("title") or "").lower()
        tmdb_imdb = str(e.get("tmdb/imdb") or "").lower()
        if q in title or q in tmdb_imdb:
            results.append({
                "serial": e.get("serial"),
                "title": e.get("title"),
                "tmdb_imdb": e.get("tmdb/imdb"),
                "hosts": _extract_all_host_urls(e),
            })
            if len(results) >= limit:
                break
    return results


def _extract_all_host_urls(entry: dict) -> list[dict]:
    """Extract and categorize all host URLs from a database entry."""
    def host_key_sort(k: str) -> int:
        m = re.search(r"host-(\d+)", k)
        return int(m.group(1)) if m else 9999

    host_keys = sorted(
        [k for k, v in entry.items() if k.startswith("host") and isinstance(v, str) and v.startswith("http")],
        key=host_key_sort
    )
    
    hosts = []
    for k in host_keys:
        url = entry[k]
        provider = detect_provider(url)
        hosts.append({
            "key": k,
            "url": url,
            "provider": provider,
            "type": get_provider_type(provider),
        })
    return hosts


# ---------------------------------------------------------------------------
# Provider Detection & Session Building
# ---------------------------------------------------------------------------

def detect_provider(url: str) -> str:
    """Detect streaming provider name from URL."""
    try:
        netloc = urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return "unknown"

    if any(alias in netloc for alias in MIXDROP_ALIASES):
        return "mixdrop"
    if any(alias in netloc for alias in STREAMTA_ALIASES):
        return "streamtape"
    if any(alias in netloc for alias in STREAMWISH_ALIASES):
        return "streamwish"
    if any(alias in netloc for alias in LULUVDOO_ALIASES):
        return "luluvdoo"
    if any(alias in netloc for alias in BYSE_ALIASES):
        return "bysejikuar"
    if any(alias in netloc for alias in DOOD_ALIASES):
        return "doodstream"
    if "voe" in netloc:
        return "voe"
    if url.endswith(".m3u8") or ".m3u8?" in url:
        return "hls_direct"
    if url.endswith(".mp4") or ".mp4?" in url:
        return "mp4_direct"
    return "unknown"


def get_provider_type(provider: str) -> str:
    """Returns 'hls' or 'mp4'."""
    if provider in ("streamwish", "luluvdoo", "bysejikuar", "voe", "hls_direct"):
        return "hls"
    return "mp4"


def _mask_proxy(p: Optional[str]) -> str:
    if not p:
        return "None"
    return p.split("@")[-1] if "@" in p else p


def get_proxy_dict(proxy_url: Optional[str] = None) -> Optional[dict]:
    p = proxy_url or os.getenv("PROXY", DEFAULT_PROXY)
    if not p:
        return None
    return {"http": p, "https": p}


def _build_session(engine: str = "requests", proxy_url: str = DEFAULT_PROXY):
    if engine == "cloudscraper" and cloudscraper is not None:
        s = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
    else:
        s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    s.proxies = get_proxy_dict(proxy_url)
    return s


def _video_id(s: str) -> str:
    s = s.strip()
    m = re.search(r"/(?:e|v|d|embed|videos|f)/([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    m2 = re.search(r"^[A-Za-z0-9_-]+$", s)
    if m2:
        return s
    return s.rstrip("/").split("/")[-1].split("?")[0]


# ---------------------------------------------------------------------------
# Specific Extractors
# ---------------------------------------------------------------------------

def extract_mixdrop(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """Extract MixDrop MP4 stream URL."""
    vid = _video_id(url_or_id)
    mirrors = ["miixdrop.top", "mixdrop.ag", "mixdrop.to", "mixdrop.sx", "mixdrop.bz"]
    last_err = None

    for mirror in mirrors:
        player_url = f"https://{mirror}/e/{vid}"
        for engine in ["requests", "cloudscraper"]:
            if engine == "cloudscraper" and cloudscraper is None:
                continue
            session = _build_session(engine=engine, proxy_url=proxy)
            try:
                resp = session.get(player_url, headers={"Referer": f"https://{mirror}/"}, timeout=(8, 15))
                if resp.status_code != 200:
                    continue
                html = resp.text
                if "File was deleted" in html or "file not found" in html.lower():
                    raise RuntimeError("File was deleted or not found on MixDrop")

                pattern = r'eval\(function\((.*?)\)\{.*?\}\((.*?)\)\)'
                data_match = re.search(pattern, html, re.DOTALL)
                if not data_match:
                    continue
                raw = data_match.group(2).replace(".split('|')", "")
                data = ast.literal_eval(raw)
                p, a, c, k = data[0], int(data[1]), int(data[2]), data[3].split('|')
                decoded = unpack(p, a, c, k)

                m = re.search(r'MDCore\.wurl="([^"]+)"', decoded)
                if not m:
                    continue

                raw_stream_url = "https:" + m.group(1) if m.group(1).startswith("//") else m.group(1)
                title_m = re.search(r'MDCore\.title="([^"]+)"', decoded)
                poster_m = re.search(r'MDCore\.poster="([^"]+)"', decoded)
                poster_url = ("https:" + poster_m.group(1)) if (poster_m and poster_m.group(1).startswith("//")) else (poster_m.group(1) if poster_m else None)

                return {
                    "status": "success",
                    "provider": "mixdrop",
                    "type": "mp4",
                    "video_id": vid,
                    "player_url": player_url,
                    "title": title_m.group(1) if title_m else "MixDrop Video",
                    "poster_url": poster_url,
                    "raw_stream_url": raw_stream_url,
                    "stream_url": f"/stream/{vid}",
                    "proxy": proxy,
                    "proxy_used": _mask_proxy(proxy),
                }
            except Exception as err:
                last_err = err

    raise RuntimeError(f"MixDrop extraction failed: {last_err}")


def extract_streamta(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """Extract Streamta / Streamtape MP4 direct stream URL."""
    vid = _video_id(url_or_id)
    canonical = "streamta.site"
    player_url = f"https://{canonical}/e/{vid}"
    last_err = None

    for engine in ["requests", "cloudscraper"]:
        if engine == "cloudscraper" and cloudscraper is None:
            continue
        session = _build_session(engine=engine, proxy_url=proxy)
        try:
            resp = session.get(player_url, headers={"Referer": f"https://{canonical}/"}, timeout=(8, 15))
            if resp.status_code != 200:
                continue
            html = resp.text
            if "File was deleted" in html or "file not found" in html.lower():
                raise RuntimeError("File was deleted or not found on Streamta")

            title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
            title = title_m.group(1).strip() if title_m else "Streamta Video"

            candidates = extract_signed_get_video_candidates(html)
            direct_stream_url = None
            for signed in candidates:
                try:
                    r2 = session.get(signed, headers={"Referer": player_url}, allow_redirects=False, timeout=(8, 15))
                    loc = r2.headers.get("Location") or r2.headers.get("location")
                    if r2.status_code in (301, 302, 303, 307, 308) and loc:
                        direct_stream_url = loc
                        break
                    if r2.status_code == 200 and ("video" in r2.headers.get("Content-Type", "") or "octet-stream" in r2.headers.get("Content-Type", "")):
                        direct_stream_url = signed
                        break
                except Exception:
                    pass

            if direct_stream_url:
                return {
                    "status": "success",
                    "provider": "streamtape",
                    "type": "mp4",
                    "video_id": vid,
                    "player_url": player_url,
                    "title": title,
                    "raw_stream_url": direct_stream_url,
                    "stream_url": f"/stream/{vid}",
                    "proxy": proxy,
                    "proxy_used": _mask_proxy(proxy),
                }
        except Exception as err:
            last_err = err

    raise RuntimeError(f"Streamtape extraction failed: {last_err}")


def extract_streamwish(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """Extract StreamWish / Playnixes HLS M3U8 stream URL."""
    vid = _video_id(url_or_id)
    canonical = "playnixes.com"
    player_url = f"https://{canonical}/e/{vid}"
    last_err = None

    for engine in ["requests", "cloudscraper"]:
        if engine == "cloudscraper" and cloudscraper is None:
            continue
        session = _build_session(engine=engine, proxy_url=proxy)
        try:
            resp = session.get(player_url, headers={"Referer": f"https://{canonical}/"}, timeout=(8, 15))
            if resp.status_code != 200:
                continue
            html = resp.text
            if "File is no longer available" in html or "file was deleted" in html.lower():
                raise RuntimeError("File was deleted on StreamWish")

            title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
            title = title_m.group(1).strip() if title_m else "StreamWish Video"

            packed_match = re.search(r"(eval\(function\(p,a,c,k,e,d\)\{.*?\.split\('\|'\)[^)]*\)\))", html, re.DOTALL)
            if not packed_match:
                continue
            decoded = unpack(packed_match.group(1))

            streams = dict(re.findall(r'"(hls[234])"\s*:\s*"([^"]+)"', decoded))
            extra = re.findall(r'https?://[^\s"\']+\.(?:m3u8|txt|mp4)\??[^\s"\']*', decoded)
            for u in extra:
                if u not in streams.values():
                    key = "hls2" if ".m3u8" in u else ("hls3" if ".txt" in u else "hls4")
                    streams.setdefault(key, u)

            selected_stream = streams.get("hls2") or streams.get("hls3") or streams.get("hls4") or (list(streams.values())[0] if streams else None)
            if selected_stream:
                return {
                    "status": "success",
                    "provider": "streamwish",
                    "type": "hls",
                    "video_id": vid,
                    "player_url": player_url,
                    "title": title,
                    "raw_stream_url": selected_stream,
                    "stream_url": f"/proxy?url={quote(selected_stream)}",
                    "proxy": proxy,
                    "proxy_used": _mask_proxy(proxy),
                }
        except Exception as err:
            last_err = err

    raise RuntimeError(f"StreamWish extraction failed: {last_err}")


def extract_luluvdoo(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """Extract Luluvdoo / Lulustream HLS M3U8 stream URL."""
    vid = _video_id(url_or_id)
    canonical = "luluvdoo.com"
    player_url = f"https://{canonical}/e/{vid}"
    last_err = None

    for engine in ["requests", "cloudscraper"]:
        if engine == "cloudscraper" and cloudscraper is None:
            continue
        session = _build_session(engine=engine, proxy_url=proxy)
        try:
            resp = session.get(player_url, headers={"Referer": f"https://{canonical}/"}, timeout=(8, 15))
            if resp.status_code != 200:
                continue
            html = resp.text
            if "File is no longer available" in html or "file was deleted" in html.lower():
                raise RuntimeError("File was deleted on Luluvdoo")

            title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
            title = title_m.group(1).strip() if title_m else "Luluvdoo Video"

            packed_match = re.search(r"(eval\(function\(p,a,c,k,e,d\)\{.*?\.split\('\|'\)[^)]*\)\))", html, re.DOTALL)
            if not packed_match:
                continue
            decoded = unpack(packed_match.group(1))

            streams = dict(re.findall(r'"(hls[234])"\s*:\s*"([^"]+)"', decoded))
            extra = re.findall(r'https?://[^\s"\']+\.(?:m3u8|txt|mp4)\??[^\s"\']*', decoded)
            for u in extra:
                if u not in streams.values():
                    key = "hls2" if ".m3u8" in u else ("hls3" if ".txt" in u else "hls4")
                    streams.setdefault(key, u)

            selected_stream = streams.get("hls2") or streams.get("hls3") or streams.get("hls4") or (list(streams.values())[0] if streams else None)
            if selected_stream:
                return {
                    "status": "success",
                    "provider": "luluvdoo",
                    "type": "hls",
                    "video_id": vid,
                    "player_url": player_url,
                    "title": title,
                    "raw_stream_url": selected_stream,
                    "stream_url": f"/proxy?url={quote(selected_stream)}",
                    "proxy": proxy,
                    "proxy_used": _mask_proxy(proxy),
                }
        except Exception as err:
            last_err = err

    raise RuntimeError(f"Luluvdoo extraction failed: {last_err}")


def extract_bysejikuar(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """Extract Bysejikuar AES-GCM encrypted HLS stream."""
    vid = _video_id(url_or_id)
    canonical = "bysejikuar.com"
    api_url = f"https://{canonical}/api/videos/{vid}"
    player_url = f"https://{canonical}/e/{vid}"
    last_err = None

    for engine in ["requests", "cloudscraper"]:
        if engine == "cloudscraper" and cloudscraper is None:
            continue
        session = _build_session(engine=engine, proxy_url=proxy)
        try:
            resp = session.get(api_url, headers={"Referer": player_url, "Origin": f"https://{canonical}"}, timeout=(8, 15))
            if resp.status_code != 200:
                continue
            data = resp.json()
            playback = data.get("playback", {})
            sources_data = decrypt_playback(playback)
            sources = sources_data.get("sources", [])
            master_m3u8 = sources[0]["url"] if sources else None
            if master_m3u8:
                return {
                    "status": "success",
                    "provider": "bysejikuar",
                    "type": "hls",
                    "video_id": vid,
                    "player_url": player_url,
                    "title": data.get("title") or "Bysejikuar Video",
                    "poster_url": data.get("poster_url") or sources_data.get("poster_url"),
                    "raw_stream_url": master_m3u8,
                    "stream_url": f"/proxy?url={quote(master_m3u8)}",
                    "proxy": proxy,
                    "proxy_used": _mask_proxy(proxy),
                }
        except Exception as err:
            last_err = err

    raise RuntimeError(f"Bysejikuar extraction failed: {last_err}")


def extract_dood(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """Extract Playmogo / DoodStream MP4 stream via pass_md5."""
    vid = _video_id(url_or_id)
    canonical = "playmogo.com"
    player_url = f"https://{canonical}/e/{vid}"
    last_err = None

    for engine in ["requests", "cloudscraper"]:
        if engine == "cloudscraper" and cloudscraper is None:
            continue
        session = _build_session(engine=engine, proxy_url=proxy)
        try:
            r = session.get(player_url, timeout=(8, 15), allow_redirects=True)
            if r.status_code != 200 or "/pass_md5/" not in r.text:
                continue
            html = r.text
            parsed = urlparse(r.url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            m = re.search(r"\$\.get\(['\"](/pass_md5/[^'\"]+)['\"]", html)
            if not m:
                continue
            pass_md5_path = m.group(1)
            token = pass_md5_path.rstrip("/").rsplit("/", 1)[-1]
            r2 = session.get(
                base + pass_md5_path,
                headers={"Referer": str(r.url), "X-Requested-With": "XMLHttpRequest"},
                timeout=(8, 15),
            )
            if r2.status_code == 200 and r2.text.strip().startswith("http"):
                raw_stream_url = r2.text.strip() + _make_dood_play(token)
                return {
                    "status": "success",
                    "provider": "doodstream",
                    "type": "mp4",
                    "video_id": vid,
                    "player_url": player_url,
                    "title": "DoodStream Video",
                    "raw_stream_url": raw_stream_url,
                    "stream_url": f"/stream/{vid}",
                    "proxy": proxy,
                    "proxy_used": _mask_proxy(proxy),
                }
        except Exception as err:
            last_err = err

    raise RuntimeError(f"DoodStream extraction failed: {last_err}")


# ---------------------------------------------------------------------------
# Universal Extractor
# ---------------------------------------------------------------------------

def extract_universal(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """Universal dispatcher that identifies provider and extracts stream."""
    url = str(url_or_id).strip()
    provider = detect_provider(url)

    if provider == "mixdrop":
        res = extract_mixdrop(url, proxy=proxy)
    elif provider == "streamtape":
        res = extract_streamta(url, proxy=proxy)
    elif provider == "streamwish":
        res = extract_streamwish(url, proxy=proxy)
    elif provider == "luluvdoo":
        res = extract_luluvdoo(url, proxy=proxy)
    elif provider == "bysejikuar":
        res = extract_bysejikuar(url, proxy=proxy)
    elif provider == "doodstream":
        res = extract_dood(url, proxy=proxy)
    elif provider in ("hls_direct", "mp4_direct"):
        stream_type = "hls" if provider == "hls_direct" else "mp4"
        res = {
            "status": "success",
            "provider": provider,
            "type": stream_type,
            "video_id": _video_id(url),
            "player_url": url,
            "title": "Direct Stream",
            "raw_stream_url": url,
            "stream_url": f"/proxy?url={quote(url)}" if stream_type == "hls" else url,
            "proxy": proxy,
            "proxy_used": _mask_proxy(proxy),
        }
    else:
        # Try extractors in sequential fallback order
        for fn in (extract_mixdrop, extract_streamwish, extract_streamta, extract_dood, extract_luluvdoo, extract_bysejikuar):
            try:
                res = fn(url, proxy=proxy)
                break
            except Exception:
                continue
        else:
            raise RuntimeError(f"Unsupported or unresolvable stream URL: {url}")

    # Cache stream for direct byte proxies
    vid = res["video_id"]
    stream_cache[vid] = {
        "raw_stream_url": res["raw_stream_url"],
        "player_url": res.get("player_url"),
        "title": res.get("title"),
        "proxy": res.get("proxy"),
        "type": res.get("type"),
        "provider": res.get("provider"),
        "extracted_at": time.time(),
    }
    return res


def extract_entry_multi_host(entry: dict, requested_host_url: Optional[str] = None) -> dict:
    """Extract stream from an entry with automatic failover across all detected host links."""
    all_hosts = _extract_all_host_urls(entry)
    if not all_hosts:
        raise RuntimeError(f"No valid host URLs found in database entry for '{entry.get('title')}'")

    # If specific host requested, try it first
    if requested_host_url:
        target_hosts = [h for h in all_hosts if h["url"] == requested_host_url] + [h for h in all_hosts if h["url"] != requested_host_url]
    else:
        target_hosts = all_hosts

    last_err = None
    for host_info in target_hosts:
        url = host_info["url"]
        provider = host_info["provider"]
        logger.info(f"Attempting extraction on host [{provider}]: {url}")
        try:
            result = extract_universal(url)
            result["title"] = entry.get("title") or result.get("title")
            result["tmdb_imdb"] = entry.get("tmdb/imdb")
            result["serial"] = entry.get("serial")
            result["available_hosts"] = all_hosts
            result["current_host"] = host_info
            return result
        except Exception as e:
            last_err = e
            logger.warning(f"Host [{provider}] {url} failed: {e}")

    raise RuntimeError(f"All {len(all_hosts)} host streams failed for '{entry.get('title')}': {last_err}")


# ---------------------------------------------------------------------------
# HTML Web Player Template
# ---------------------------------------------------------------------------

def render_player_html(stream_data: dict) -> str:
    """Generate dynamic responsive Glassmorphism Player UI with Multi-Host Switcher."""
    title = stream_data.get("title") or "Universal Stream Player"
    stream_url = stream_data.get("stream_url") or ""
    stream_type = stream_data.get("type", "mp4")
    provider = (stream_data.get("provider") or "Universal").upper()
    proxy_used = stream_data.get("proxy_used", "Active")
    tmdb_imdb = stream_data.get("tmdb_imdb") or ""
    serial = stream_data.get("serial") or ""
    poster = stream_data.get("poster_url") or ""
    available_hosts = stream_data.get("available_hosts") or []
    current_host_url = (stream_data.get("current_host") or {}).get("url", "")

    # Host switch buttons HTML
    host_buttons_html = ""
    for idx, h in enumerate(available_hosts, start=1):
        is_active = (h["url"] == current_host_url)
        p_name = h["provider"].upper()
        badge_cls = "host-badge active" if is_active else "host-badge"
        encoded_url = quote(h["url"])
        host_buttons_html += f"""
        <button onclick="switchHost('{encoded_url}')" class="{badge_cls}">
            <span class="dot"></span> {p_name} (#{idx})
        </button>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — Universal Stream Player</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.7/dist/hls.min.js"></script>
    <style>
        :root {{
            --bg: #07090e;
            --card-bg: rgba(18, 22, 34, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent: #6366f1;
            --accent-glow: rgba(99, 102, 241, 0.35);
            --cyan: #06b6d4;
            --emerald: #10b981;
            --text: #f3f4f6;
            --text-dim: #9ca3af;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            overflow-x: hidden;
        }}
        /* Ambient background glow */
        .ambient-glow {{
            position: fixed;
            top: -20%;
            left: 50%;
            transform: translateX(-50%);
            width: 800px;
            height: 500px;
            background: radial-gradient(circle, var(--accent-glow) 0%, rgba(6, 182, 212, 0.15) 50%, transparent 80%);
            filter: blur(80px);
            z-index: 0;
            pointer-events: none;
        }}
        .header {{
            width: 100%;
            max-width: 1200px;
            padding: 1.5rem 1.5rem 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            z-index: 10;
        }}
        .logo-box {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            text-decoration: none;
            color: var(--text);
        }}
        .logo-icon {{
            width: 38px;
            height: 38px;
            background: linear-gradient(135deg, var(--accent), var(--cyan));
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 1.2rem;
            box-shadow: 0 4px 20px var(--accent-glow);
        }}
        .logo-title {{
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(to right, #fff, #9ca3af);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .search-bar {{
            display: flex;
            align-items: center;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--card-border);
            border-radius: 9999px;
            padding: 0.4rem 0.6rem 0.4rem 1rem;
            gap: 0.5rem;
            backdrop-filter: blur(12px);
        }}
        .search-input {{
            background: transparent;
            border: none;
            color: var(--text);
            font-family: inherit;
            font-size: 0.9rem;
            outline: none;
            width: 220px;
        }}
        .search-btn {{
            background: var(--accent);
            border: none;
            color: white;
            padding: 0.4rem 0.9rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .search-btn:hover {{
            background: #4f46e5;
            box-shadow: 0 0 12px var(--accent-glow);
        }}
        .main-container {{
            width: 100%;
            max-width: 1200px;
            padding: 0 1.5rem 3rem;
            z-index: 10;
        }}
        .player-wrapper {{
            background: #000;
            border-radius: 16px;
            border: 1px solid var(--card-border);
            overflow: hidden;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8), 0 0 30px rgba(99, 102, 241, 0.15);
            position: relative;
            aspect-ratio: 16 / 9;
            width: 100%;
        }}
        video {{
            width: 100%;
            height: 100%;
            display: block;
            outline: none;
        }}
        .meta-card {{
            margin-top: 1.5rem;
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
        }}
        .title-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 1rem;
        }}
        .video-title {{
            font-size: 1.6rem;
            font-weight: 700;
            letter-spacing: -0.5px;
        }}
        .pill-container {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
        }}
        .pill {{
            padding: 0.35rem 0.8rem;
            border-radius: 8px;
            font-size: 0.8rem;
            font-weight: 600;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
        .pill-provider {{ background: rgba(99, 102, 241, 0.2); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.4); }}
        .pill-type {{ background: rgba(6, 182, 212, 0.2); color: #22d3ee; border: 1px solid rgba(6, 182, 212, 0.4); }}
        .pill-id {{ background: rgba(255, 255, 255, 0.08); color: var(--text-dim); font-family: 'JetBrains Mono', monospace; }}
        .hosts-section {{
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(255, 255, 255, 0.06);
        }}
        .section-label {{
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .host-switcher {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.6rem;
        }}
        .host-badge {{
            display: flex;
            align-items: center;
            gap: 0.4rem;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--card-border);
            color: var(--text-dim);
            padding: 0.45rem 0.9rem;
            border-radius: 10px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .host-badge:hover {{
            background: rgba(255, 255, 255, 0.1);
            color: var(--text);
            border-color: rgba(255, 255, 255, 0.2);
        }}
        .host-badge.active {{
            background: linear-gradient(135deg, var(--accent), #4f46e5);
            color: #fff;
            border-color: transparent;
            box-shadow: 0 4px 15px var(--accent-glow);
        }}
        .dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: currentColor;
        }}
        .footer-info {{
            margin-top: 2rem;
            text-align: center;
            font-size: 0.85rem;
            color: var(--text-dim);
        }}
        @media(max-width: 768px) {{
            .header {{ flex-direction: column; gap: 1rem; align-items: stretch; }}
            .search-bar {{ width: 100%; }}
            .search-input {{ width: 100%; }}
            .title-row {{ flex-direction: column; }}
        }}
    </style>
</head>
<body>
    <div class="ambient-glow"></div>
    
    <header class="header">
        <a href="/" class="logo-box">
            <div class="logo-icon">&#9654;</div>
            <div class="logo-title">UniversalStream</div>
        </a>
        <form class="search-bar" onsubmit="handleSearch(event)">
            <input type="text" id="searchInput" class="search-input" placeholder="TMDB ID, IMDb (tt...), or Movie Title..." value="{tmdb_imdb.split('/')[0] if tmdb_imdb else ''}">
            <button type="submit" class="search-btn">Play</button>
        </form>
    </header>

    <main class="main-container">
        <div class="player-wrapper">
            <video id="videoPlayer" controls autoplay playsinline poster="{poster}"></video>
        </div>

        <div class="meta-card">
            <div class="title-row">
                <h1 class="video-title">{title}</h1>
                <div class="pill-container">
                    <span class="pill pill-provider">{provider}</span>
                    <span class="pill pill-type">{stream_type.upper()}</span>
                    <span class="pill pill-id">{tmdb_imdb or f"SERIAL #{serial}"}</span>
                </div>
            </div>

            <div class="hosts-section">
                <span class="section-label">Available Stream Hosts (Click to Switch):</span>
                <div class="host-switcher">
                    {host_buttons_html if host_buttons_html else '<span style="color:var(--text-dim);font-size:0.85rem;">Single Host Direct Play</span>'}
                </div>
            </div>
        </div>

        <div class="footer-info">
            Universal Multi-Host Stream Server & Player &bull; Fast Proxy Pipeline &bull; Proxy: {proxy_used}
        </div>
    </main>

    <script>
        const streamUrl = "{stream_url}";
        const streamType = "{stream_type}";
        const video = document.getElementById("videoPlayer");

        function initPlayer() {{
            if (!streamUrl) return;

            if (streamType === "hls") {{
                if (Hls.isSupported()) {{
                    const hls = new Hls({{
                        enableWorker: true,
                        lowLatencyMode: true,
                        backBufferLength: 90
                    }});
                    hls.loadSource(streamUrl);
                    hls.attachMedia(video);
                    hls.on(Hls.Events.MANIFEST_PARSED, function() {{
                        video.play().catch(e => console.log("Autoplay blocked:", e));
                    }});
                }} else if (video.canPlayType("application/vnd.apple.mpegurl")) {{
                    video.src = streamUrl;
                    video.play().catch(e => console.log("Autoplay blocked:", e));
                }}
            }} else {{
                video.src = streamUrl;
                video.play().catch(e => console.log("Autoplay blocked:", e));
            }}
        }}

        function switchHost(encodedHostUrl) {{
            const currentUrl = new URL(window.location.href);
            currentUrl.searchParams.set("host_url", decodeURIComponent(encodedHostUrl));
            window.location.href = currentUrl.toString();
        }}

        function handleSearch(e) {{
            e.preventDefault();
            const val = document.getElementById("searchInput").value.trim();
            if (!val) return;
            if (val.startsWith("http")) {{
                window.location.href = "/api/direct/" + encodeURIComponent(val);
            }} else if (val.toLowerCase().startsWith("tt")) {{
                window.location.href = "/api/" + val;
            }} else if (/^\\d+$/.test(val)) {{
                window.location.href = "/api/" + val;
            }} else {{
                window.location.href = "/api/db/search?q=" + encodeURIComponent(val);
            }}
        }}

        // Keyboard Shortcuts
        document.addEventListener("keydown", (e) => {{
            if (document.activeElement.tagName === "INPUT") return;
            if (e.code === "Space") {{
                e.preventDefault();
                video.paused ? video.play() : video.pause();
            }} else if (e.code === "ArrowRight") {{
                video.currentTime += 10;
            }} else if (e.code === "ArrowLeft") {{
                video.currentTime -= 10;
            }} else if (e.code === "KeyF") {{
                if (!document.fullscreenElement) {{
                    document.querySelector(".player-wrapper").requestFullscreen().catch(err => {{}});
                }} else {{
                    document.exitFullscreen();
                }}
            }}
        }});

        initPlayer();
    </script>
</body>
</html>
"""


def render_home_html() -> str:
    """Generate sleek landing page with statistics, database explorer, and stream player."""
    db_len = len(get_db())
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Universal Stream Player & API</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #07090e;
            --card-bg: rgba(18, 22, 34, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent: #6366f1;
            --cyan: #06b6d4;
            --emerald: #10b981;
            --text: #f3f4f6;
            --text-dim: #9ca3af;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Outfit', sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2rem 1.5rem;
        }}
        .ambient-glow {{
            position: fixed;
            top: -20%;
            left: 50%;
            transform: translateX(-50%);
            width: 900px;
            height: 600px;
            background: radial-gradient(circle, rgba(99, 102, 241, 0.25) 0%, rgba(6, 182, 212, 0.1) 50%, transparent 80%);
            filter: blur(90px);
            z-index: 0;
            pointer-events: none;
        }}
        .container {{
            width: 100%;
            max-width: 1100px;
            z-index: 10;
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }}
        .hero {{
            text-align: center;
            padding: 3rem 1rem 1rem;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            background: rgba(99, 102, 241, 0.15);
            border: 1px solid rgba(99, 102, 241, 0.3);
            color: #a5b4fc;
            padding: 0.4rem 1rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 1.25rem;
        }}
        .hero-title {{
            font-size: 3rem;
            font-weight: 800;
            letter-spacing: -1px;
            background: linear-gradient(135deg, #fff 30%, #9ca3af 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 1rem;
        }}
        .hero-subtitle {{
            color: var(--text-dim);
            font-size: 1.15rem;
            max-width: 650px;
            margin: 0 auto 2rem;
            line-height: 1.6;
        }}
        .search-box-large {{
            max-width: 650px;
            margin: 0 auto;
            display: flex;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 0.6rem 0.6rem 0.6rem 1.25rem;
            gap: 0.75rem;
            backdrop-filter: blur(20px);
            box-shadow: 0 10px 35px rgba(0, 0, 0, 0.5);
        }}
        .search-box-large input {{
            flex: 1;
            background: transparent;
            border: none;
            color: #fff;
            font-family: inherit;
            font-size: 1.05rem;
            outline: none;
        }}
        .search-box-large button {{
            background: linear-gradient(135deg, var(--accent), #4f46e5);
            border: none;
            color: white;
            padding: 0.75rem 1.75rem;
            border-radius: 12px;
            font-weight: 700;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 4px 15px var(--accent-glow);
        }}
        .search-box-large button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 6px 20px var(--accent-glow);
        }}
        .grid-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(20px);
        }}
        .card-title {{
            font-size: 1.1rem;
            font-weight: 700;
            margin-bottom: 0.75rem;
            color: #fff;
        }}
        .card-p {{
            color: var(--text-dim);
            font-size: 0.9rem;
            line-height: 1.5;
            margin-bottom: 1rem;
        }}
        .endpoints-list {{
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }}
        .endpoint-item {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            background: rgba(0, 0, 0, 0.4);
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.04);
            color: #38bdf8;
            display: flex;
            justify-content: space-between;
        }}
        .endpoint-item a {{
            color: inherit;
            text-decoration: none;
        }}
        .endpoint-item a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="ambient-glow"></div>
    <div class="container">
        <div class="hero">
            <div class="badge">&#9889; {db_len:,} Entries Loaded &bull; Multi-Host Auto-Failover</div>
            <h1 class="hero-title">Universal Stream Player & API</h1>
            <p class="hero-subtitle">High-performance unified streaming engine for MixDrop, StreamWish, Streamtape, DoodStream, Luluvdoo, and Bysejikuar.</p>
            
            <form class="search-box-large" onsubmit="handleSearch(event)">
                <input type="text" id="searchInput" placeholder="Enter TMDB ID (e.g. 68), IMDb (tt0088846), or direct URL...">
                <button type="submit">Play Now</button>
            </form>
        </div>

        <div class="grid-cards">
            <div class="card">
                <h3 class="card-title">&#127916; Quick Play Examples</h3>
                <p class="card-p">Test instantly with popular entries in the dataset:</p>
                <ul class="endpoints-list">
                    <li class="endpoint-item"><a href="/api/68">/api/68 &rarr; Brazil (TMDB)</a></li>
                    <li class="endpoint-item"><a href="/api/tt0088846">/api/tt0088846 &rarr; Brazil (IMDb)</a></li>
                    <li class="endpoint-item"><a href="/api/515248">/api/515248 &rarr; Streamta / Dood Host</a></li>
                    <li class="endpoint-item"><a href="/api/20197">/api/20197 &rarr; StreamWish HLS</a></li>
                </ul>
            </div>

            <div class="card">
                <h3 class="card-title">&#128268; Core API Endpoints</h3>
                <p class="card-p">Integrate directly into your frontend or player apps:</p>
                <ul class="endpoints-list">
                    <li class="endpoint-item"><a href="/api/db/stats">GET /api/db/stats</a> <span>Database Stats</span></li>
                    <li class="endpoint-item"><a href="/api/db/search?q=star">GET /api/db/search?q=...</a> <span>Title Search</span></li>
                    <li class="endpoint-item"><a href="/healthz">GET /healthz</a> <span>Service Health</span></li>
                    <li class="endpoint-item"><a href="/api/68?format=json">GET /api/:id?format=json</a> <span>Raw Stream JSON</span></li>
                </ul>
            </div>
        </div>
    </div>

    <script>
        function handleSearch(e) {{
            e.preventDefault();
            const val = document.getElementById("searchInput").value.trim();
            if (!val) return;
            if (val.startsWith("http")) {{
                window.location.href = "/api/direct/" + encodeURIComponent(val);
            }} else if (val.toLowerCase().startsWith("tt") || /^\\d+$/.test(val)) {{
                window.location.href = "/api/" + val;
            }} else {{
                window.location.href = "/api/db/search?q=" + encodeURIComponent(val);
            }}
        }}
    </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    if request.headers.get("Accept") == "application/json" or request.args.get("format") == "json":
        return jsonify({
            "service": "Universal Stream API & Multi-Host Player",
            "status": "online",
            "db_entries": len(get_db()),
            "proxy": _mask_proxy(DEFAULT_PROXY),
            "endpoints": {
                "health": "/healthz",
                "tmdb_lookup": "/api/<int:tmdb_id>",
                "imdb_lookup": "/api/<imdb_id>",
                "direct_stream": "/api/direct/<url>",
                "extract_post": "/api/extract (POST json: {url: ...})",
                "db_stats": "/api/db/stats",
                "db_search": "/api/db/search?q=<query>",
                "stream_proxy": "/stream/<video_id>",
                "hls_segment_proxy": "/proxy?url=<target_url>",
            }
        })
    return render_home_html()


@app.route("/healthz")
def healthz():
    return jsonify({"status": "healthy", "timestamp": time.time(), "db_count": len(get_db())})


@app.route("/api/db/stats")
def db_stats():
    db = get_db()
    return jsonify({
        "status": "success",
        "total_entries": len(db),
        "fetched_at": _db_fetched_at,
        "db_url": DB_URL,
        "proxy": _mask_proxy(DEFAULT_PROXY),
    })


@app.route("/api/db/search")
def db_search():
    q = request.args.get("q", "")
    if not q:
        return jsonify({"status": "error", "message": "Missing 'q' query parameter"}), 400
    results = search_db(q)
    return jsonify({"status": "success", "query": q, "count": len(results), "results": results})


@app.route("/api/<path:query_id>")
def api_lookup(query_id: str):
    """Universal ID Lookup (TMDB ID, IMDb ID, serial, or title)."""
    # Exclude direct or reserved routes
    if query_id.startswith("direct/") or query_id.startswith("db/"):
        return Response("Not found", status=404)

    entry = lookup_any(query_id)
    if not entry:
        return jsonify({"status": "error", "message": f"No database entry found for query '{query_id}'"}), 404

    requested_host = request.args.get("host_url")
    try:
        result = extract_entry_multi_host(entry, requested_host_url=requested_host)
    except Exception as e:
        logger.error(f"Multi-host extraction error for {query_id}: {e}")
        return jsonify({"status": "error", "message": str(e), "entry": entry}), 502

    # Return JSON or HTML player
    if request.headers.get("Accept") == "application/json" or request.args.get("format") == "json":
        return jsonify(result)
    return render_player_html(result)


@app.route("/api/direct/<path:direct_url>")
def api_direct(direct_url: str):
    """Extract and play any direct stream provider URL."""
    try:
        res = extract_universal(direct_url)
    except Exception as e:
        logger.error(f"Direct extraction error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 502

    if request.headers.get("Accept") == "application/json" or request.args.get("format") == "json":
        return jsonify(res)
    return render_player_html(res)


@app.route("/api/extract", methods=["POST"])
def api_extract_post():
    """POST endpoint for JSON extract requests: {"url": "..."}."""
    body = request.get_json(silent=True) or {}
    url = body.get("url")
    if not url:
        return jsonify({"status": "error", "message": "Missing 'url' in request body"}), 400
    try:
        res = extract_universal(url)
        return jsonify(res)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 502


# ---------------------------------------------------------------------------
# MP4 Video Proxy (/stream/<video_id>)
# ---------------------------------------------------------------------------

@app.route("/stream/<video_id>")
def stream_proxy(video_id: str):
    """Proxy MP4 video bytes supporting Range requests (206 Partial Content)."""
    cached = stream_cache.get(video_id)
    if not cached:
        # Try finding in DB or extracting directly
        entry = lookup_any(video_id)
        if entry:
            try:
                res = extract_entry_multi_host(entry)
                cached = stream_cache.get(res["video_id"])
            except Exception:
                pass

    if not cached:
        return Response("Video stream not found or expired. Please re-request /api/<id>.", status=404)

    raw_stream_url = cached["raw_stream_url"]
    proxy = cached.get("proxy") or os.getenv("PROXY", DEFAULT_PROXY)
    proxy_dict = get_proxy_dict(proxy)

    req_headers = {
        "User-Agent": UA,
        "Referer": cached.get("player_url") or raw_stream_url,
        "Accept": "*/*",
    }
    if "Range" in request.headers:
        req_headers["Range"] = request.headers["Range"]

    try:
        upstream = requests.get(
            raw_stream_url,
            headers=req_headers,
            proxies=proxy_dict,
            stream=True,
            timeout=(10, 60),
            allow_redirects=True,
        )

        resp_headers = {}
        for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "Content-Disposition"):
            if h in upstream.headers:
                resp_headers[h] = upstream.headers[h]

        resp_headers["Access-Control-Allow-Origin"] = "*"
        resp_headers["Access-Control-Allow-Headers"] = "Range, Content-Type, Authorization"
        resp_headers["Access-Control-Expose-Headers"] = "Content-Range, Content-Length, Accept-Ranges"

        def generate():
            for chunk in upstream.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    yield chunk

        return Response(
            stream_with_context(generate()),
            status=upstream.status_code,
            headers=resp_headers,
        )
    except Exception as e:
        logger.error(f"Stream proxy error {video_id}: {e}")
        return Response(f"Stream proxy error: {e}", status=502)


# ---------------------------------------------------------------------------
# HLS Master & TS Segment Proxy (/proxy?url=<target_url>)
# ---------------------------------------------------------------------------

@app.route("/proxy")
def hls_proxy():
    """Proxy and rewrite HLS M3U8 playlists & MPEG-TS segments."""
    target_url = request.args.get("url")
    if not target_url:
        return Response("Missing 'url' query parameter", status=400)

    target_url = unquote(target_url)
    proxy = os.getenv("PROXY", DEFAULT_PROXY)
    proxy_dict = get_proxy_dict(proxy)

    headers = {
        "User-Agent": UA,
        "Referer": f"{urlparse(target_url).scheme}://{urlparse(target_url).netloc}/",
        "Accept": "*/*",
    }
    if "Range" in request.headers:
        headers["Range"] = request.headers["Range"]

    try:
        r = requests.get(
            target_url,
            headers=headers,
            proxies=proxy_dict,
            stream=True,
            timeout=(10, 30),
            allow_redirects=True,
        )

        content_type = r.headers.get("Content-Type", "")

        # If M3U8 playlist, rewrite URLs to route through /proxy
        if any(kw in content_type.lower() for kw in ("mpegurl", "m3u8")) or target_url.endswith(".m3u8") or ".m3u8?" in target_url:
            text = r.text
            base_url = r.url
            rewritten_lines = []
            for line in text.splitlines():
                line_str = line.strip()
                if not line_str:
                    rewritten_lines.append(line)
                    continue

                if line_str.startswith("#EXT-X-KEY") or line_str.startswith("#EXT-X-MAP"):
                    def rewrite_uri(match):
                        full = urljoin(base_url, match.group(1))
                        return f'URI="/proxy?url={quote(full)}"'
                    line = re.sub(r'URI="([^"]+)"', rewrite_uri, line)
                    rewritten_lines.append(line)
                elif not line_str.startswith("#"):
                    full_seg_url = urljoin(base_url, line_str)
                    rewritten_lines.append(f"/proxy?url={quote(full_seg_url)}")
                else:
                    rewritten_lines.append(line)

            rewritten_manifest = "\n".join(rewritten_lines)
            resp = Response(rewritten_manifest, status=200, mimetype="application/vnd.apple.mpegurl")
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "*"
            resp.headers["Cache-Control"] = "no-cache"
            return resp

        # TS segment / binary pass-through
        resp_headers = {}
        for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
            if h in r.headers:
                resp_headers[h] = r.headers[h]

        resp_headers["Access-Control-Allow-Origin"] = "*"
        resp_headers["Access-Control-Allow-Headers"] = "*"
        resp_headers["Access-Control-Expose-Headers"] = "Content-Range, Content-Length, Accept-Ranges"

        def generate():
            for chunk in r.iter_content(chunk_size=512 * 1024):
                if chunk:
                    yield chunk

        return Response(stream_with_context(generate()), status=r.status_code, headers=resp_headers)
    except Exception as e:
        logger.error(f"HLS proxy error for {target_url}: {e}")
        return Response(f"Proxy error: {e}", status=502)


# ---------------------------------------------------------------------------
# Server Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    logger.info(f"UniversalStream API & Player starting on :{port} | Proxy: {_mask_proxy(DEFAULT_PROXY)}")
    app.run(host="0.0.0.0", port=port, debug=False)
