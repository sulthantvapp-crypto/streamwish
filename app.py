from flask import Flask, request, jsonify
from urllib.parse import quote
import requests
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_PROXY = "default_proxy"
VOE_WORKER_BASE = "https://voe-sx-movies-play.ytbro8326.workers.dev"

def _video_id(url_or_id: str) -> str:
    return url_or_id.strip().split('/')[-1]

def extract_voe(url_or_id: str, proxy: str = DEFAULT_PROXY) -> dict:
    """0. VOE.sx Extractor - Modified to extract direct .m3u8/.mp4 stream URL."""
    clean = str(url_or_id).strip()
    
    # Query the dedicated VOE worker API
    worker_api = f"{VOE_WORKER_BASE.rstrip('/')}/api/{clean}"
    try:
        r = requests.get(worker_api, timeout=(10, 20))
        if r.status_code == 200:
            data = r.json()
            if data.get("success"):
                # ഡയറക്ട് .m3u8 അല്ലെങ്കിൽ mp4 ലിങ്ക് എടുത്തു മാറ്റുന്നു
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
                    "tmdb_imdb": data.get("tm
