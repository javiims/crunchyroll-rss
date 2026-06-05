import re
import os
import time
import requests
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

LINKS_FILE = "links.txt"
RSS_FILE = "feed.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

def load_links():
    if not os.path.exists(LINKS_FILE):
        return []
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def save_links(urls):
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        for url in urls:
            f.write(url + "\n")

def load_or_create_rss():
    if os.path.exists(RSS_FILE):
        tree = ET.parse(RSS_FILE)
        rss = tree.getroot()
    else:
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "Crunchyroll Prime Video - Novedades Accesibilidad"
        ET.SubElement(channel, "link").text = "https://www.primevideo.com"
        ET.SubElement(channel, "description").text = "Detección automática de audiodescripción, audio estándar y subtítulos CC en Español (España)"
        tree = ET.ElementTree(rss)
    return tree, rss

def normalize_url(url):
    if "/-/es/" not in url:
        return url.replace("primevideo.com/", "primevideo.com/-/es/", 1)
    return url

def extract_title(html):
    m = re.search(r'"parentTitle":"([^"]+)"', html)
    if m: return m.group(1)
    m = re.search(r"<title>Prime Video:\s*(.+?)</title>", html)
    return m.group(1).strip() if m else "Título desconocido"

def search_in_html(html):
    detected = []
    clean = re.sub(r"\s+", " ", html)

    if re.search(r'Español\s*\(España\)\s*\[descripci[oó]n\s+de\s+audio\]', clean, re.IGNORECASE):
        detected.append("Audiodescripción")

    if re.search(r'Español\s*\(España\)\s*\[CC\]', clean, re.IGNORECASE):
        detected.append("Subtítulos CC")
        
    audio_match = re.search(r'"audioTracks"\s*:\s*\[(.*?)\]', clean, re.IGNORECASE)
    if audio_match and re.search(r'"español\s*\(españa\)"', audio_match.group(1).lower()):
        detected.append("Audio Estándar")

    return detected

def fetch_url(url, session):
    try:
        r = session.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.text
    except:
        return None

def add_rss_item(channel, title, url, detected_types):
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = url
    ET.SubElement(item, "description").text = "Detectado: " + " | ".join(detected_types) + " en Español (España)"
    ET.SubElement(item, "pubDate").text = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

def main():
    urls = load_links()
    if not urls: return

    tree, rss = load_or_create_rss()
    channel = rss.find("channel")
    pending_urls = []
    found_any = False
    session = requests.Session()

    for url in urls:
        html = fetch_url(normalize_url(url), session)
        if not html:
            pending_urls.append(url)
            continue

        detected_types = search_in_html(html)
        if detected_types:
            add_rss_item(channel, extract_title(html), url, detected_types)
            found_any = True
        else:
            pending_urls.append(url)
        time.sleep(2)

    save_links(pending_urls)
    if found_any:
        tree.write(RSS_FILE, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    main()
