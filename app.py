import re
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
    """0. VOE.sx Extractor - Direct M3U8/MP4 Regex Extraction"""
    clean = str(url_or_id).strip()
    vid = _video_id(clean)
    
    target_url = f"{VOE_WORKER_BASE.rstrip('/')}/{clean}"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(target_url, headers=headers, timeout=(10, 20), allow_redirects=True)
        if r.status_code == 200:
            content = r.text
            
            # HTML പേജിൽ നിന്ന് .m3u8 അല്ലെങ്കിൽ .mp4 ലിങ്ക് തപ്പിപ്പിടിക്കുന്നു
            m3u8_match = re.search(r'(https?://[^\s<>"]+?\.m3u8[^\s<>"]*)', content)
            mp4_match = re.search(r'(https?://[^\s<>"]+?\.mp4[^\s<>"]*)', content)
            
            direct_url = None
            if m3u8_match:
                direct_url = m3u8_match.group(1)
            elif mp4_match:
                direct_url = mp4_match.group(1)
            
            # ലിങ്ക് കിട്ടിയില്ലെങ്കിൽ ടാർഗെറ്റ് URL തന്നെ fallback ആയി വെക്കാം
            final_stream_url = direct_url if direct_url else target_url
            
            return {
                "status": "success",
                "provider": "voe",
                "type": "hls",
                "video_id": vid,
                "player_url": target_url,
                "title": "VOE Stream",
                "stream_url": final_stream_url, # ഇപ്പൊ നേരെ m3u8/mp4 ലിങ്ക് കിട്ടും!
                "proxy": proxy,
                "proxy_used": "voe-worker",
            }
    except Exception as e:
        logger.warning(f"VOE extraction error for {clean}: {e}")

    raise RuntimeError(f"VOE extraction failed for {clean}")

@app.route("/extract", methods=["GET"])
def extract():
    url_or_id = request.args.get("url")
    if not url_or_id:
        return jsonify({"status": "error", "message": "URL missing"}), 400
    try:
        result = extract_voe(url_or_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
