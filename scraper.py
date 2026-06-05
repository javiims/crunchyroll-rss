import re
import os
import time
import requests
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

LINKS_FILE = "links.txt"
RSS_FILE = "feed.xml"

# Headers que simulan un navegador real
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
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}


def load_links():
    if not os.path.exists(LINKS_FILE):
        return []
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines


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
        ET.SubElement(channel, "description").text = (
            "Detección automática de audiodescripción, audio estándar y subtítulos CC en Español (España)"
        )
        tree = ET.ElementTree(rss)
    return tree, rss


def normalize_url(url):
    """Fuerza el directorio de idioma español en la URL."""
    if "/-/es/" not in url:
        url = url.replace("primevideo.com/", "primevideo.com/-/es/", 1)
    return url


def extract_title(html):
    m = re.search(r'"parentTitle":"([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r"<title>Prime Video:\s*(.+?)</title>", html)
    if m:
        return m.group(1).strip()
    return "Título desconocido"


def search_in_html(html):
    """Busca los patrones de accesibilidad y doblaje en el HTML."""
    detected = []
    clean = re.sub(r"\s+", " ", html)

    if re.search(r'Español\s*\(España\)\s*\[descripci[oó]n\s+de\s+audio\]', clean, re.IGNORECASE):
        detected.append("Audiodescripción")

    if re.search(r'Español\s*\(España\)\s*\[CC\]', clean, re.IGNORECASE):
        detected.append("Subtítulos CC")
        
    audio_match = re.search(r'"audioTracks"\s*:\s*\[(.*?)\]', clean, re.IGNORECASE)
    if audio_match:
        audio_data = audio_match.group(1).lower()
        if re.search(r'"español\s*\(españa\)"', audio_data):
            detected.append("Audio Estándar")

    return detected


def get_spanish_proxies():
    """Descarga una lista de proxies HTTP gratuitos de España desde ProxyScrape."""
    print("  [DEBUG] Solicitando lista de proxies gratuitos de España...")
    try:
        url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=ES&ssl=all&anonymity=all"
        response = requests.get(url, timeout=10)
        proxies = [p.strip() for p in response.text.split('\n') if p.strip()]
        print(f"  [DEBUG] Se han encontrado {len(proxies)} proxies españoles disponibles.")
        # Devolvemos solo los primeros 10 para no eternizar la ejecución si fallan
        return proxies[:10]
    except Exception as e:
        print(f"  [DEBUG] Fallo al obtener proxies españoles: {e}")
        return []


def fetch_url_with_proxy(url, session, proxy_list):
    """Intenta descargar la web pasando por la lista de proxies hasta que uno funcione."""
    for proxy_ip in proxy_list:
        proxies = {
            "http": f"http://{proxy_ip}",
            "https": f"http://{proxy_ip}"
        }
        print(f"  [DEBUG] Intentando conectar a través del proxy: {proxy_ip}")
        try:
            # Ponemos un timeout corto (15s) porque los proxies gratuitos suelen quedarse colgados
            r = session.get(url, headers=HEADERS, proxies=proxies, timeout=15)
            r.raise_for_status()
            
            # Comprobamos si Amazon nos ha tirado un CAPTCHA por usar un proxy sospechoso
            if "api-services-support@amazon.com" in r.text or "To discuss automated access to Amazon data please contact" in r.text:
                print("  [DEBUG] Amazon detectó el proxy y bloqueó el acceso (CAPTCHA).")
                continue
                
            print(f"  [DEBUG] ¡Conexión exitosa a través del proxy {proxy_ip}!")
            
            # Guardamos el HTML para poder depurar
            with open("debug_codigo.html", "w", encoding="utf-8") as f:
                f.write(r.text)
                
            return r.text
        except Exception as e:
            print(f"  [DEBUG] Falló la conexión con el proxy {proxy_ip}: {e}")

    # Si todos los proxies fallan (o no hay proxies), intentamos sin proxy como último recurso
    print("  [DEBUG] Agotados los proxies de España. Intentando conexión directa desde GitHub...")
    try:
        r = session.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        with open("debug_codigo.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        return r.text
    except Exception as e:
        print(f"  [DEBUG] Falló la conexión directa: {e}")
        return None


def add_rss_item(channel, title, url, detected_types):
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = url
    description = "Detectado: " + " | ".join(detected_types) + " en Español (España)"
    ET.SubElement(item, "description").text = description
    pub_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    ET.SubElement(item, "pubDate").text = pub_date


def main():
    urls = load_links()
    if not urls:
        print("No hay enlaces que comprobar.")
        return

    tree, rss = load_or_create_rss()
    channel = rss.find("channel")
    pending_urls = []
    found_any = False

    session = requests.Session()
    
    # Cargamos la lista de IPs españolas una sola vez al inicio
    spanish_proxies = get_spanish_proxies()

    for url in urls:
        print(f"\nComprobando: {url}")
        try:
            norm_url = normalize_
