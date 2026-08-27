"""
Universal Stream Player & Multi-Host API Server

Exact Luluvdoo Fluid Player UI & Priority Stream Pipeline:
0. VOE.sx (voe-sx-movies-play worker)
1. DoodStream / Playmogo
2. MixDrop
3. Luluvdoo / Lulustream
4. Bysejikuar / Bikebyse
5. StreamWish / Playnixes
6. Streamta / Streamtape
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

# Provider Priority Order
# 0. VOE.sx (voe-sx-movies-play worker) -> 1. dood -> 2. mixdrop -> 3. luluvdo -> 4. bysejikuarcom -> 5. streamwish -> 6. streamta
PROVIDER_PRIORITY = {
    "voe": 0,
    "doodstream": 1,
    "mixdrop": 2,
    "luluvdoo": 3,
    "bysejikuar": 4,
    "streamwish": 5,
    "streamtape": 6,
    "unknown": 99,
}

VOE_WORKER_BASE = os.getenv("VOE_WORKER_BASE", "https://voe-sx-movies-play.ytbro8326.workers.dev")

VOE_ALIASES = {
    "voe.sx", "voe-sx-movies-play.ytbro8326.workers.dev", "tracylocalschool.com",
    "audaciousdefrauded.com", "reputationscreaming.com", "tupmishk.com",
}

DOOD_ALIASES = {
    "dood.watch", "dood.so", "dood.li", "doods.pro",
    "vidply.com", "ds2play.com", "ds2video.com", "d-s.io",
    "d000d.com", "d0000d.com", "dood.ws", "dood.pm",
    "dood.re", "dood.to", "playmogo.com",
}

MIXDROP_ALIASES = {
    "mixdrop.ag", "mixdrop.co", "mixdrop.to", "mixdrop.sx", "mixdrop.bz",
    "mixdrop.ch", "mixdrop.is", "mixdrop.vc", "mixdrop.club", "mixdrop.si",
    "miiixdrop.net", "mixdrop.nu", "mixdrop.vip", "mixdrop.ps", "mixdrop.cat",
    "mixdrop.click", "mixdrop.space", "miixdrop.top",
}

LULUVDOO_ALIASES = {
    "luluvdoo.com", "luluvdo.com", "luluvid.com", "lulustream.com",
    "luluvstream.com", "luluvdo.net", "lulustream.to", "luluvdoo.to",
}

BYSE_ALIASES = {
    "bysejikuar.com", "bikebyse.com", "byse.com", "bysejikuar",
}

STREAMWISH_ALIASES = {
    "streamwish.to", "streamwish.com", "playnixes.com", "swishsrv.com",
    "flaswish.com", "streamwish.site", "streamwish.xyz", "wishembed.pro",
    "embedwish.com", "awish.pro", "streamwish.org", "filelions.to",
}

STREAMTA_ALIASES = {
    "streamta.site", "streamtape.com", "streamtape.net", "streamtape.to",
    "streamta.to", "streamta.com", "streamtape.xyz", "streamta.co",
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
# JS Unpackers & Decryptors
# ---------------------------------------------------------------------------

def unpack(p, a=None, c=None, k=None, e=None, d=None):
    """Deobfuscator for packed JavaScript functions."""
    if a is None and c is None and k is None:
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
    """Generate Doodstream stream token path."""
    rnd = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
    return f"{rnd}?token={token}&expiry={int(time.time() * 1000)}"


# ---------------------------------------------------------------------------
# Database Helpers
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
        try:
            headers = {
                "Accept": "application/vnd.github.v3.raw, application/json, text/plain, */*",
                "User-Agent": "Universal-Stream-API/1.0",
            }
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                logger.info(f"DB loaded successfully: {len(data)} entries (via {url})")
                return data
        except Exception as err:
            logger.debug(f"Direct DB fetch {url} failed: {err}")

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
                    logger.debug(f"Auth DB fetch failed: {err}")

    # Fallback to local bundled database.json
    for local_file in ["database.json", "custom_merged_data.json"]:
        if os.path.exists(local_file):
            try:
                with open(local_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info(f"DB loaded successfully from local '{local_file}': {len(data)} entries")
                    return data
            except Exception as e:
                logger.warning(f"Failed to read local DB '{local_file}': {e}")

    logger.error("DB fetch failed: unable to fetch from remote or local fallback")
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
    q = str(query_id).strip()
    if not q:
        return None

    entry = lookup_by_tmdb(q)
    if entry:
        return entry

    if q.lower().startswith("tt") or (q.isdigit() and len(q) >= 7):
        entry = lookup_by_imdb(q)
        if entry:
            return entry

    if q.isdigit():
        q_int = int(q)
        for e in get_db():
            if e.get("serial") == q_int:
                return e

    q_low = q.lower()
    for e in get_db():
        t = str(e.get("title") or "").lower()
        if q_low == t:
            return e

    return None


def search_db(query: str, limit: int = 20) -> list[dict]:
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
    """Extract and sort host URLs according to user-specified priority order."""
    def host_priority_sort(h: dict) -> int:
        provider = h["provider"]
        return PROVIDER_PRIORITY.get(provider, 99)

    host_keys = [k for k, v in entry.items() if k.startswith("host") and isinstance(v, str) and v.startswith("http")]
    
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

    # Sort strictly by priority: 1. dood -> 2. mixdrop -> 3. luluvdo -> 4. bysejikuar -> 5. streamwish -> 6. streamta
    return sorted(hosts, key=host_priority_sort)


# ---------------------------------------------------------------------------
# Provider Detection & Networking
# ---------------------------------------------------------------------------

def detect_provider(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return "unknown"

    if any(alias in netloc for alias in VOE_ALIASES):
        return "voe"
    if any(alias in netloc for alias in DOOD_ALIASES):
        return "doodstream"
    if any(alias in netloc for alias in MIXDROP_ALIASES):
        return "mixdrop"
    if any(alias in netloc for alias in LULUVDOO_ALIASES):
        return "luluvdoo"
    if any(alias in netloc for alias in BYSE_ALIASES):
        return "bysejikuar"
    if any(alias in netloc for alias in STREAMWISH_ALIASES):
        return "streamwish"
    if any(alias in netloc for alias in STREAMTA_ALIASES):
        return "streamtape"
    if url.endswith(".m3u8") or ".m3u8?" in url:
        return "hls_direct"
    if url.endswith(".mp4") or ".mp4?" in url:
        return "mp4_direct"
    return "unknown"


def get_provider_type(provider: str) -> str:
    if provider in ("voe", "streamwish", "luluvdoo", "bysejikuar", "hls_direct"):
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
# Individual Extractors
# ---------------------------------------------------------------------------

def extract_voe(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """0. VOE.sx Extractor via https://voe-sx-movies-play.ytbro8326.workers.dev."""
    clean = str(url_or_id).strip()
    
    # Query the dedicated VOE worker API directly with TMDB ID, IMDB ID, or VOE URL
    worker_api = f"{VOE_WORKER_BASE.rstrip('/')}/api/{clean}"
    try:
        r = requests.get(worker_api, timeout=(10, 20))
        if r.status_code == 200:
            data = r.json()
            if data.get("success"):
                stream_url = data.get("proxied_stream_url") or data.get("stream_url")
                raw_stream_url = data.get("stream_url") or stream_url
                vid = _video_id(clean)
                return {
                    "status": "success",
                    "provider": "voe",
                    "type": "hls",
                    "video_id": vid,
                    "player_url": data.get("host_used") or f"{VOE_WORKER_BASE.rstrip('/')}/{clean}",
                    "title": data.get("title") or "VOE Stream",
                    "tmdb_imdb": data.get("tmdb_imdb"),
                    "raw_stream_url": raw_stream_url,
                    "stream_url": stream_url,
                    "proxy": proxy,
                    "proxy_used": "voe-worker",
                }
    except Exception as e:
        logger.warning(f"VOE worker extraction error for {clean}: {e}")

    raise RuntimeError(f"VOE extraction failed for {clean}")


def extract_dood(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """1. DoodStream / Playmogo Extractor."""
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


def extract_mixdrop(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """2. MixDrop Extractor."""
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


def extract_luluvdoo(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """3. Luluvdoo / Lulustream Extractor."""
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
                    "stream_url": f"/stream/{vid}.m3u8",
                    "proxy": proxy,
                    "proxy_used": _mask_proxy(proxy),
                }
        except Exception as err:
            last_err = err

    raise RuntimeError(f"Luluvdoo extraction failed: {last_err}")


def extract_bysejikuar(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """4. Bysejikuar / Bikebyse Extractor (AES-GCM Decryption)."""
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


def extract_streamwish(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """5. StreamWish / Playnixes Extractor."""
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


def extract_streamta(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """6. Streamta / Streamtape Extractor."""
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


# ---------------------------------------------------------------------------
# Universal Extraction & Pipeline Ordering
# ---------------------------------------------------------------------------

def extract_universal(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """Extract stream based on URL detection or waterfall fallback."""
    url = str(url_or_id).strip()
    provider = detect_provider(url)

    if provider == "voe":
        res = extract_voe(url, proxy=proxy)
    elif provider == "doodstream":
        res = extract_dood(url, proxy=proxy)
    elif provider == "mixdrop":
        res = extract_mixdrop(url, proxy=proxy)
    elif provider == "luluvdoo":
        res = extract_luluvdoo(url, proxy=proxy)
    elif provider == "bysejikuar":
        res = extract_bysejikuar(url, proxy=proxy)
    elif provider == "streamwish":
        res = extract_streamwish(url, proxy=proxy)
    elif provider == "streamtape":
        res = extract_streamta(url, proxy=proxy)
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
        # Fallback strictly in requested priority: voe -> dood -> mixdrop -> luluvdo -> bysejikuar -> streamwish -> streamta
        for fn in (extract_voe, extract_dood, extract_mixdrop, extract_luluvdoo, extract_bysejikuar, extract_streamwish, extract_streamta):
            try:
                res = fn(url, proxy=proxy)
                break
            except Exception:
                continue
        else:
            raise RuntimeError(f"Unsupported or unresolvable stream URL: {url}")

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
    """
    Extract stream with priority order:
    1. dood -> 2. mixdrop -> 3. luluvdo -> 4. bysejikuar -> 5. streamwish -> 6. streamta
    """
    all_hosts = _extract_all_host_urls(entry)
    if not all_hosts:
        raise RuntimeError(f"No valid host URLs found in database entry for '{entry.get('title')}'")

    if requested_host_url:
        target_hosts = [h for h in all_hosts if h["url"] == requested_host_url] + [h for h in all_hosts if h["url"] != requested_host_url]
    else:
        target_hosts = all_hosts

    last_err = None
    for host_info in target_hosts:
        url = host_info["url"]
        provider = host_info["provider"]
        logger.info(f"Trying host in priority order [{provider}]: {url}")
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
            logger.warning(f"Host [{provider}] failed: {e}")

    raise RuntimeError(f"All host streams failed for '{entry.get('title')}': {last_err}")


# ---------------------------------------------------------------------------
# Exact Luluvdoo Player UI Template
# ---------------------------------------------------------------------------

LULUVDOO_PLAYER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.8/dist/hls.min.js"></script>
<style>
  :root {{
    --bg-main: #070913;
    --accent: #3b82f6;
    --accent-hover: #60a5fa;
  }}
  * {{margin:0;padding:0;box-sizing:border-box;}}
  html,body {{
    width:100%;height:100%;background:var(--bg-main);
    overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    color:#fff;
  }}
  .player-wrapper {{
    position:relative;width:100%;height:100%;
    display:flex;align-items:center;justify-content:center;
    background:#000;
  }}
  video {{
    width:100%;height:100%;display:block;
    object-fit:contain;background:#000;outline:none;
  }}
  #unmuteBtn {{
    display:none; position:absolute; top:24px; right:24px; z-index:100;
    background:rgba(15,23,42,0.85); color:#fff; border:1px solid rgba(255,255,255,0.25);
    padding:10px 20px; border-radius:30px; font-size:14px; font-weight:600; cursor:pointer;
    backdrop-filter:blur(10px); display:flex; align-items:center; gap:8px;
    box-shadow:0 10px 25px rgba(0,0,0,0.6); transition:all 0.2s ease;
  }}
  #unmuteBtn:hover {{background:rgba(30,41,59,0.95); transform:scale(1.05); border-color:var(--accent);}}
  
  .badge-bar {{
    position:absolute; top:24px; left:24px; z-index:50;
    display:flex; align-items:center; gap:10px; pointer-events:none;
  }}
  .badge {{
    background:rgba(15,23,42,0.75); backdrop-filter:blur(8px);
    border:1px solid rgba(255,255,255,0.15); border-radius:20px;
    padding:6px 14px; font-size:12px; font-weight:600; color:#cbd5e1;
    display:flex; align-items:center; gap:6px;
  }}
  .badge span.dot {{
    width:8px; height:8px; border-radius:50%; background:#22c55e;
    display:inline-block; box-shadow:0 0 8px #22c55e;
  }}
  
  #err {{
    display:none; position:fixed; inset:0; align-items:center; justify-content:center;
    flex-direction:column; color:#f87171; font-family:system-ui,sans-serif;
    font-size:1rem; background:#070913; text-align:center; padding:30px; gap:14px; z-index:99;
  }}
  #err button {{
    background:var(--accent); color:#fff; border:none; border-radius:8px;
    padding:10px 24px; font-size:14px; font-weight:600; cursor:pointer;
    margin-top:10px; transition:background 0.2s;
  }}
  #err button:hover {{background:var(--accent-hover);}}
  #err small {{color:#94a3b8; font-size:0.85rem;}}
</style>
</head>
<body>

<div class="player-wrapper">
  <div class="badge-bar">
    <div class="badge"><span class="dot"></span> {provider_label} Stream</div>
    <div id="qualityBadge" class="badge" style="display:none;">Auto</div>
  </div>

  <video id="v" controls autoplay playsinline preload="auto"></video>
  
  <button id="unmuteBtn" onclick="toggleUnmute()">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>
    <span>Click to Unmute</span>
  </button>
</div>

<div id="err">
  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
  <div style="font-size:18px; font-weight:700; color:#f1f5f9;">Stream Unavailable</div>
  <div>The video stream could not be loaded or the link expired.</div>
  <small>Reload the stream or try another host.</small>
  <button onclick="window.location.reload()">Reload Player</button>
</div>

<script>
  const video = document.getElementById("v");
  const errBox = document.getElementById("err");
  const unmuteBtn = document.getElementById("unmuteBtn");
  const qualityBadge = document.getElementById("qualityBadge");
  const streamUrl = "{stream_url}";
  const streamType = "{stream_type}";

  function showError() {{
    errBox.style.display = "flex";
  }}

  function toggleUnmute() {{
    video.muted = false;
    unmuteBtn.style.display = "none";
  }}

  function tryAutoPlay() {{
    video.play().then(() => {{
      if (video.muted) {{
        unmuteBtn.style.display = "flex";
      }}
    }}).catch(() => {{
      video.muted = true;
      video.play().then(() => {{
        unmuteBtn.style.display = "flex";
      }}).catch(showError);
    }});
  }}

  if (streamType === "hls") {{
    if (Hls.isSupported()) {{
      const hls = new Hls({{
        debug: false,
        enableWorker: true,
        lowLatencyMode: false,
        maxBufferLength: 60,
        maxMaxBufferLength: 120,
        xhrSetup: function(xhr, url) {{
          xhr.withCredentials = false;
        }}
      }});

      hls.loadSource(streamUrl);
      hls.attachMedia(video);

      hls.on(Hls.Events.MANIFEST_PARSED, function(event, data) {{
        if (data.levels && data.levels.length > 0) {{
          qualityBadge.style.display = "flex";
          const h = data.levels[0].height || (data.levels[1] ? data.levels[1].height : null);
          qualityBadge.textContent = h ? `${{h}}p` : "HD";
        }}
        tryAutoPlay();
      }});

      hls.on(Hls.Events.LEVEL_SWITCHED, function(event, data) {{
        const level = hls.levels[data.level];
        if (level && level.height) {{
          qualityBadge.textContent = `${{level.height}}p`;
        }}
      }});

      hls.on(Hls.Events.ERROR, function(event, data) {{
        if (data.fatal) {{
          switch(data.type) {{
            case Hls.ErrorTypes.NETWORK_ERROR:
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              hls.destroy();
              showError();
              break;
          }}
        }}
      }});
    }} else if (video.canPlayType("application/vnd.apple.mpegurl")) {{
      video.src = streamUrl;
      video.addEventListener("loadedmetadata", tryAutoPlay);
      video.onerror = showError;
    }} else {{
      showError();
    }}
  }} else {{
    // Direct MP4 stream (Dood, Mixdrop, Streamtape)
    video.src = streamUrl;
    video.addEventListener("loadedmetadata", tryAutoPlay);
    video.onerror = showError;
    tryAutoPlay();
  }}

  // Keyboard Shortcuts: Space (Play/Pause), Left/Right (Seek 10s), F (Fullscreen), M (Mute)
  window.addEventListener("keydown", (e) => {{
    if (["Space", "ArrowLeft", "ArrowRight", "KeyF", "KeyM"].includes(e.code)) {{
      e.preventDefault();
      if (e.code === "Space") video.paused ? video.play() : video.pause();
      if (e.code === "ArrowLeft") video.currentTime = Math.max(0, video.currentTime - 10);
      if (e.code === "ArrowRight") video.currentTime = Math.min(video.duration, video.currentTime + 10);
      if (e.code === "KeyF") document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
      if (e.code === "KeyM") video.muted = !video.muted;
    }}
  }});
</script>
</body>
</html>"""


def _wants_html(req) -> bool:
    if req.args.get("format") == "json":
        return False
    accept = req.headers.get("Accept", "")
    return "text/html" in accept or "*/*" in accept


def _player_response(data: dict) -> Response:
    provider = (data.get("provider") or "Universal").capitalize()
    html = LULUVDOO_PLAYER_HTML.format(
        title=data.get("title") or "Stream Player",
        stream_url=data.get("stream_url", ""),
        stream_type=data.get("type", "mp4"),
        provider_label=provider,
    )
    return Response(html, content_type="text/html")


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route("/")
def root():
    return jsonify({
        "service": "universal-stream-api",
        "status": "online",
        "load_priority": [
            "0. VOE.sx (voe-sx-movies-play worker)",
            "1. DoodStream (playmogo)",
            "2. MixDrop",
            "3. Luluvdoo (lulustream)",
            "4. Bysejikuar (bikebyse)",
            "5. StreamWish (playnixes)",
            "6. Streamta (streamtape)",
        ],
        "db_entries": len(get_db()),
        "endpoints": {
            "tmdb": "/api/<tmdb_id>",
            "imdb": "/api/<imdb_id>",
            "direct": "/api/direct/<url_or_id>",
            "stream": "/stream/<video_id>",
            "proxy": "/proxy?url=<target_url>",
            "db_stats": "/api/db/stats",
            "db_search": "/api/db/search?q=<query>",
            "health": "/healthz",
        }
    })


@app.route("/healthz")
def healthz():
    return jsonify({"status": "healthy", "service": "universal-stream-api", "db_count": len(get_db()), "timestamp": time.time()})


@app.route("/api/db/stats")
def db_stats():
    db = get_db()
    return jsonify({
        "status": "success",
        "total_entries": len(db),
        "fetched_at": _db_fetched_at,
        "db_url": DB_URL,
        "proxy": _mask_proxy(DEFAULT_PROXY),
        "priority": ["voe", "dood", "mixdrop", "luluvdoo", "bysejikuar", "streamwish", "streamtape"]
    })


@app.route("/api/db/search")
def db_search():
    q = request.args.get("q", "")
    if not q:
        return jsonify({"status": "error", "message": "Missing 'q' query parameter"}), 400
    results = search_db(q)
    return jsonify({"status": "success", "query": q, "count": len(results), "results": results})


@app.route("/api/<int:tmdb_id>")
def api_tmdb(tmdb_id: int):
    """GET /api/<tmdb_id> - checks VOE worker server first; if playing, plays immediately, else shifts to DB/other hosts."""
    # 1. First check VOE server directly for this TMDB ID
    if not request.args.get("host_url"):
        try:
            logger.info(f"Checking VOE server first for TMDB ID {tmdb_id}")
            voe_res = extract_voe(str(tmdb_id))
            voe_res["id_type"] = "tmdb"
            voe_res["id_value"] = tmdb_id
            return _player_response(voe_res) if _wants_html(request) else jsonify(voe_res)
        except Exception as e:
            logger.info(f"VOE worker not found or failed for TMDB {tmdb_id}: {e}. Auto-shifting to other hosts.")

    # 2. Shift to database lookup and other multi-host providers
    entry = lookup_by_tmdb(str(tmdb_id))
    if not entry:
        return jsonify({"error": f"TMDB ID '{tmdb_id}' not found in database"}), 404
    try:
        data = extract_entry_multi_host(entry, requested_host_url=request.args.get("host_url"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    data["id_type"] = "tmdb"
    data["id_value"] = tmdb_id
    return _player_response(data) if _wants_html(request) else jsonify(data)


@app.route("/api/<path:query_id>")
def api_query_handler(query_id: str):
    """Universal router for IMDB ID (tt...), direct video IDs, and DB lookups."""
    if query_id.startswith("db/"):
        return Response("Not found", status=404)

    cleaned = query_id.strip()

    # 1. Direct URL
    if cleaned.startswith("http:/") or cleaned.startswith("https:/") or any(alias in cleaned for alias in (VOE_ALIASES | DOOD_ALIASES | MIXDROP_ALIASES | LULUVDOO_ALIASES | BYSE_ALIASES | STREAMWISH_ALIASES | STREAMTA_ALIASES)):
        return api_direct(cleaned)

    # 2. Check VOE server first if it's a numeric ID (TMDB/Serial) or IMDb ID (tt...)
    if not request.args.get("host_url") and (cleaned.isdigit() or cleaned.lower().startswith("tt")):
        try:
            logger.info(f"Checking VOE server first for query ID {cleaned}")
            voe_res = extract_voe(cleaned)
            voe_res["id_type"] = "imdb" if cleaned.lower().startswith("tt") else "tmdb"
            voe_res["id_value"] = cleaned
            return _player_response(voe_res) if _wants_html(request) else jsonify(voe_res)
        except Exception as e:
            logger.info(f"VOE worker check failed for {cleaned}: {e}. Auto-shifting to other hosts.")

    # 3. Database lookup (IMDb tt... or serial or TMDB)
    entry = lookup_any(cleaned)
    if entry:
        try:
            data = extract_entry_multi_host(entry, requested_host_url=request.args.get("host_url"))
            data["id_type"] = "imdb" if cleaned.lower().startswith("tt") else "query"
            data["id_value"] = cleaned
            return _player_response(data) if _wants_html(request) else jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # 4. Direct video ID
    return api_direct(cleaned)


@app.route("/api/direct/<path:direct_url>")
def api_direct(direct_url: str):
    if direct_url.startswith("https:/") and not direct_url.startswith("https://"):
        direct_url = "https://" + direct_url[7:]
    elif direct_url.startswith("http:/") and not direct_url.startswith("http://"):
        direct_url = "http://" + direct_url[6:]

    try:
        result = extract_universal(direct_url)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result["id_type"] = "direct"
    return _player_response(result) if _wants_html(request) else jsonify(result)


@app.route("/api/extract", methods=["POST"])
def api_extract_post():
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
# Video & HLS Proxies
# ---------------------------------------------------------------------------

@app.route("/stream/<path:video_id>")
def stream_proxy(video_id: str):
    """Handles MP4 Range proxying and Luluvdoo M3U8 rewrite proxying."""
    clean_vid = video_id.replace(".m3u8", "").replace(".ts", "")
    cached = stream_cache.get(clean_vid)
    if not cached:
        entry = lookup_any(clean_vid)
        if entry:
            try:
                res = extract_entry_multi_host(entry)
                cached = stream_cache.get(res["video_id"])
            except Exception:
                pass

    if not cached:
        return Response("Stream not found or expired.", status=404)

    raw_url = cached["raw_stream_url"]
    stream_type = cached.get("type", "mp4")
    proxy = cached.get("proxy") or os.getenv("PROXY", DEFAULT_PROXY)
    proxy_dict = get_proxy_dict(proxy)

    # M3U8 handling
    if stream_type == "hls" or video_id.endswith(".m3u8"):
        try:
            upstream = requests.get(
                raw_url,
                headers={"User-Agent": UA, "Accept": "*/*"},
                proxies=proxy_dict,
                timeout=(10, 20),
            )
            if upstream.status_code != 200:
                return Response(f"Upstream returned {upstream.status_code}", status=upstream.status_code)

            base_url = raw_url.rsplit("/", 1)[0] + "/"
            rewritten_lines = []
            for line in upstream.text.splitlines():
                line_str = line.strip()
                if not line_str:
                    continue
                if line_str.startswith("#"):
                    if 'URI="' in line_str:
                        def replace_uri(match):
                            return f'URI="/proxy?url={quote(urljoin(base_url, match.group(1)))}"'
                        line_str = re.sub(r'URI="([^"]+)"', replace_uri, line_str)
                    rewritten_lines.append(line_str)
                else:
                    rewritten_lines.append(f"/proxy?url={quote(urljoin(base_url, line_str))}")

            resp_headers = {
                "Content-Type": "application/vnd.apple.mpegurl; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "Cache-Control": "no-cache",
            }
            return Response("\n".join(rewritten_lines) + "\n", status=200, headers=resp_headers)
        except Exception as e:
            return Response(f"M3U8 Proxy error: {e}", status=502)

    # MP4 Range handling
    req_headers = {
        "User-Agent": UA,
        "Referer": cached.get("player_url") or raw_url,
        "Accept": "*/*",
    }
    if "Range" in request.headers:
        req_headers["Range"] = request.headers["Range"]

    try:
        upstream = requests.get(
            raw_url,
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


@app.route("/proxy")
def hls_segment_proxy():
    """Proxies TS segments / nested M3U8 files with CORS headers."""
    target_url = request.args.get("url")
    if not target_url:
        return Response("Missing target url", status=400)

    target_url = unquote(target_url)
    proxy = os.getenv("PROXY", DEFAULT_PROXY)
    proxy_dict = get_proxy_dict(proxy)

    req_headers = {
        "User-Agent": UA,
        "Referer": f"{urlparse(target_url).scheme}://{urlparse(target_url).netloc}/",
        "Accept": "*/*",
    }
    if "Range" in request.headers:
        req_headers["Range"] = request.headers["Range"]

    try:
        upstream = requests.get(
            target_url,
            headers=req_headers,
            proxies=proxy_dict,
            stream=True,
            timeout=(10, 30),
            allow_redirects=True,
        )

        c_type = upstream.headers.get("Content-Type", "video/MP2T")
        is_playlist = (".m3u8" in target_url or ".txt" in target_url or "mpegurl" in c_type.lower())

        if is_playlist:
            base_url = target_url.rsplit("/", 1)[0] + "/"
            rewritten_lines = []
            for line in upstream.text.splitlines():
                line_str = line.strip()
                if not line_str:
                    continue
                if line_str.startswith("#"):
                    if 'URI="' in line_str:
                        def replace_uri(match):
                            return f'URI="/proxy?url={quote(urljoin(base_url, match.group(1)))}"'
                        line_str = re.sub(r'URI="([^"]+)"', replace_uri, line_str)
                    rewritten_lines.append(line_str)
                else:
                    rewritten_lines.append(f"/proxy?url={quote(urljoin(base_url, line_str))}")

            resp_headers = {
                "Content-Type": "application/vnd.apple.mpegurl; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Cache-Control": "no-cache",
            }
            return Response("\n".join(rewritten_lines) + "\n", status=200, headers=resp_headers)

        resp_headers = {
            "Content-Type": c_type,
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Cache-Control": "public, max-age=3600",
        }
        if "Content-Length" in upstream.headers:
            resp_headers["Content-Length"] = upstream.headers["Content-Length"]
        if "Content-Range" in upstream.headers:
            resp_headers["Content-Range"] = upstream.headers["Content-Range"]

        def generate():
            try:
                for chunk in upstream.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        return Response(
            stream_with_context(generate()),
            status=upstream.status_code,
            headers=resp_headers,
            direct_passthrough=True,
        )
    except Exception as e:
        logger.error(f"Segment proxy error: {e}")
        return Response(f"Segment proxy error: {e}", status=502)


# ---------------------------------------------------------------------------
# Server Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    logger.info(f"UniversalStream server starting on :{port} | Proxy: {_mask_proxy(DEFAULT_PROXY)}")
    app.run(host="0.0.0.0", port=port, debug=False)
