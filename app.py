from flask import Flask, request, render_template, session
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL
from urllib.parse import urlparse, urljoin, parse_qs
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import validators
import time
from collections import defaultdict
import os
import re

app = Flask(__name__)
app.secret_key = "replace_with_your_secure_random_secret_key"  # Must set for sessions!

ALLOWED_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".m4a"
)

def has_allowed_extension(url):
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)

    # Debug print to see URLs being checked
    print(f"Checking URL: {url}")

    # Accept URLs with standard allowed extensions
    if any(path.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        print(" -> Allowed by extension")
        return True

    # Accept URLs with /media/ in path (common in Twitter image URLs)
    if "/media/" in path:
        print(" -> Allowed by /media/ path")
        return True

    # Accept URLs with 'format' query param matching allowed extensions (no dot)
    format_param = query.get("format", [])
    if format_param and any(f".{format_param[0].lower()}" == ext for ext in ALLOWED_EXTENSIONS):
        print(" -> Allowed by format query param")
        return True

    print(" -> Not allowed")
    return False


def extract_assets_with_selenium(url):
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("window-size=1920x1080")
        chrome_options.add_argument("user-agent=Mozilla/5.0")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome('./drivers/chromedriver', options=chrome_options)

        print(f"[DEBUG] Loading URL: {url}")
        driver.get(url)
        time.sleep(5)  # Increased wait time for JS & images to load

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")

        assets = []

        # Scan regular media tags
        tags = soup.find_all(["img", "audio", "video", "source"])
        print(f"[DEBUG] Found {len(tags)} media tags (img, audio, video, source)")

        for tag in tags:
            for attr in ["src", "data-src", "data-srcset"]:
                src = tag.get(attr)
                if src:
                    full_url = urljoin(url, src)
                    print(f"[DEBUG] Found media tag URL: {full_url}")
                    if has_allowed_extension(full_url):
                        print(f" -> Accepted by extension")
                        assets.append(full_url)
                    else:
                        print(f" -> Rejected by extension")

            if tag.name in ["audio", "video"]:
                for source_tag in tag.find_all("source"):
                    src = source_tag.get("src")
                    if src:
                        full_url = urljoin(url, src)
                        print(f"[DEBUG] Found <source> in {tag.name}: {full_url}")
                        if has_allowed_extension(full_url):
                            print(f" -> Accepted by extension")
                            assets.append(full_url)
                        else:
                            print(f" -> Rejected by extension")

        # Check Open Graph meta tags
        og_tags = [meta for meta in soup.find_all("meta") if meta.get("property") in ("og:image", "og:video")]
        print(f"[DEBUG] Found {len(og_tags)} Open Graph media tags")

        for meta_tag in og_tags:
            content = meta_tag.get("content")
            print(f"[DEBUG] Open Graph content URL: {content}")
            if content and has_allowed_extension(content):
                print(f" -> Accepted by extension")
                assets.append(content)
            else:
                print(f" -> Rejected by extension")

        # Regex fallback: find all Twitter media URLs containing /media/
        twitter_media_pattern = re.compile(r'https://pbs\.twimg\.com/media/[^\s"\'<>]+')
        twitter_media_urls = twitter_media_pattern.findall(page_source)

        print(f"[DEBUG] Twitter media URLs found by regex: {len(twitter_media_urls)}")
        for url_candidate in twitter_media_urls:
            print(f"[DEBUG] Twitter media candidate: {url_candidate}")

        for url_candidate in twitter_media_urls:
            full_url = urljoin(url, url_candidate)
            parsed = urlparse(full_url)

            # Accept if path contains /media/ or query has format param
            if "/media/" in parsed.path or "format=" in parsed.query:
                if has_allowed_extension(full_url) or "pbs.twimg.com/media" in full_url:
                    print(f"[DEBUG] Accepted Twitter media URL: {full_url}")
                    assets.append(full_url)
                else:
                    print(f"[DEBUG] Rejected Twitter media URL by extension: {full_url}")
            else:
                print(f"[DEBUG] Twitter media URL missing /media/ or format= query: {full_url}")

        driver.quit()

        # Remove duplicates but preserve order
        seen = set()
        unique_assets = []
        for a in assets:
            if a not in seen:
                unique_assets.append(a)
                seen.add(a)

        print(f"[DEBUG] Returning {len(unique_assets)} unique assets")
        return unique_assets

    except Exception as e:
        try:
            driver.quit()
        except:
            pass
        return [f"Selenium error: {e}"]

def extract_assets_with_ytdlp(url):
    try:
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "forceurl": True,
            "extract_flat": False,
        }
        assets = []

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if "entries" in info:
                info = info["entries"][0]

            formats = info.get("formats", [])

            # Filter formats we care about
            filtered_formats = [
                f for f in formats
                if f.get("url") and has_allowed_extension_ytdlp(f["url"])
            ]

            best_by_extension = {}

            for fmt in filtered_formats:
                ext = fmt.get("ext", "no_extension")
                quality_score = 0

                # Determine quality score (video: resolution, audio: bitrate)
                if fmt.get("vcodec") != "none":
                    quality_score = fmt.get("height", 0)
                elif fmt.get("acodec") != "none":
                    quality_score = fmt.get("abr", 0)

                # Store best per extension
                if ext not in best_by_extension or quality_score > best_by_extension[ext][1]:
                    best_by_extension[ext] = (fmt["url"], quality_score)

            # Return list of (url, ext)
            assets = [(url, f".{ext}") for ext, (url, _) in best_by_extension.items()]

        return assets or [("yt-dlp found video, but no suitable formats.", "no_extension")]

    except Exception as e:
        return []

def has_allowed_extension_ytdlp(url):
    """Relaxed extension check for yt-dlp streams, includes URLs with no extension but common video params."""
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        return True
    # Accept YouTube's typical streaming URLs that contain 'videoplayback'
    if "videoplayback" in url:
        return True
    return False

@app.route("/clear_cache", methods=["POST"])
def clear_cache():
    session.pop("history", None)
    return "Cache cleared", 200

@app.route("/", methods=["GET", "POST"]) 
def index():
    if "history" not in session:
        session["history"] = []

    lsd_mode = session.get("lsd_mode", False)  # Read LSD mode once at start

    error = None
    grouped_assets = {}
    submitted_url = None
    total_count = 0
    special_response = None

    if request.method == "POST":
        url = request.form.get("url", "").strip()
        submitted_url = url

        # Handle "clear"
        if url.lower() == "clear":
            session["history"] = []
            session["lsd_mode"] = False  # Disable LSD mode too
            return render_template("index.html", history=[], lsd_mode=False)

        # Handle "ping"
        if url.lower() == "ping":
            special_response = "Pong!"
            entry = {
                "url": submitted_url,
                "special_response": special_response,
                "grouped_assets": {},
                "error": None,
                "total_count": 0,
                "lsd_mode": lsd_mode,
            }
            history = session["history"]
            history.append(entry)
            session["history"] = history
            return render_template("index.html", history=history, lsd_mode=lsd_mode)
        
        # Handle "menu"
        if url.lower() == "menu":
            special_response = (
                "<br>"
                "[Menu]<br>"
                "<strong>'clear'</strong> = Clears cached results<br>"
                "<strong>'info'</strong> = Site information<br>"
                "<strong>'LSD'</strong> =  Increased efficiency<br>"
                "<strong>'exit'</strong> = Exits site<br>"
                "<br>"
                
            )
            entry = {
                "url": submitted_url,
                "special_response": special_response,
                "grouped_assets": {},
                "error": None,
                "total_count": 0,
                "lsd_mode": lsd_mode,
            }
            history = session["history"]
            history.append(entry)
            session["history"] = history
            return render_template("index.html", history=history, lsd_mode=lsd_mode)
        
        # Handle "info"
        if url.lower() == "info":
            special_response = (
                "<br>"
                "(C) 2093 Rip.farm Corporation.<br>"
                "<br>"
                "Use rip.farm responsibly! We do not endorse unauthorized distribution of copyrighted material.<br>"
                "<br>"
            )
            entry = {
                "url": submitted_url,
                "special_response": special_response,
                "grouped_assets": {},
                "error": None,
                "total_count": 0,
                "lsd_mode": lsd_mode,
            }
            history = session["history"]
            history.append(entry)
            session["history"] = history
            return render_template("index.html", history=history, lsd_mode=lsd_mode)
        
        # Handle "exit"
        if url.lower() == "exit":
            special_response = "Exiting..."
            entry = {
                "url": submitted_url,
                "special_response": special_response,
                "grouped_assets": {},
                "error": None,
                "total_count": 0,
                "lsd_mode": lsd_mode,
            }
            history = session["history"]
            history.append(entry)
            session["history"] = history
            return render_template("index.html", history=history, lsd_mode=lsd_mode)
        
        # Toggle "lsd" mode
        if url.lower() == "lsd":
            current = session.get("lsd_mode", False)
            session["lsd_mode"] = not current
            lsd_mode = session["lsd_mode"]
            special_response = f"LSD mode {'enabled.' if lsd_mode else 'disabled.'}"

            entry = {
                "url": submitted_url,
                "special_response": special_response,
                "grouped_assets": {},
                "error": None,
                "total_count": 0,
                "lsd_mode": lsd_mode,
            }

            history = session["history"]
            history.append(entry)
            session["history"] = history

            return render_template("index.html", history=history, lsd_mode=lsd_mode)

        if not url:
            error = "Please enter a URL."
        else:
            if not validators.url(url):
                url_with_scheme = "https://" + url
                if validators.url(url_with_scheme):
                    error = f"Invalid URL. Did you mean {url_with_scheme}?"
                else:
                    error = "Invalid URL."
            else:
                try:
                    media_urls = []
                    html_assets = extract_assets_with_selenium(url)

                    if any(domain in url for domain in ["soundcloud.com", "youtube.com", "youtu.be", "vimeo.com", "twitter.com", "x.com"]):
                        media_urls = extract_assets_with_ytdlp(url)

                    # Normalize html_assets into (url, ext)
                    html_assets = [(u, os.path.splitext(urlparse(u).path)[1].lower() or "no_extension") for u in html_assets]

                    all_assets = media_urls + html_assets

                    seen = set()
                    assets = []
                    for asset in all_assets:
                        if asset[0] not in seen:
                            assets.append(asset)
                            seen.add(asset[0])

                    grouped = defaultdict(list)
                    for url, ext in assets:
                        ext = f".{ext}" if not ext.startswith(".") else ext
                        grouped[ext].append(url)

                    grouped_assets = {ext: sorted(urls) for ext, urls in sorted(grouped.items())}
                    total_count = sum(len(urls) for urls in grouped_assets.values())

                except Exception as e:
                    error = f"Unhandled error: {e}"

        entry = {
            "url": submitted_url,
            "grouped_assets": grouped_assets,
            "error": error,
            "total_count": total_count,
            "special_response": special_response,
            "lsd_mode": lsd_mode,
        }

        history = session["history"]
        history.append(entry)
        session["history"] = history

    return render_template("index.html", history=session.get("history", []), lsd_mode=lsd_mode)
if __name__ == "__main__":
    app.run(debug=True)
