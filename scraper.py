import re
import os
import time
import requests
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

LINKS_FILE = "links.txt"
RSS_FILE = "feed.xml"

# Headers que simulan un navegador real para evitar bloqueos anti-bot
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}


def load_links():
    """Carga la lista de URLs a rastrear desde el archivo de texto."""
    if not os.path.exists(LINKS_FILE):
        return []
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines


def save_links(urls):
    """Guarda la lista actualizada de URLs pendientes."""
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        for url in urls:
            f.write(url + "\n")


def load_or_create_rss():
    """Carga el RSS existente o crea uno nuevo."""
    if os.path.exists(RSS_FILE):
        tree = ET.parse(RSS_FILE)
        rss = tree.getroot()
    else:
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "Crunchyroll Prime Video - Novedades Accesibilidad"
        ET.SubElement(channel, "link").text = "https://www.primevideo.com"
        ET.SubElement(channel, "description").text = (
            "Detección automática de audiodescripción y subtítulos CC en Español (España)"
        )
        tree = ET.ElementTree(rss)
    return tree, rss


def normalize_url(url):
    """
    Normaliza la URL para forzar el idioma español en Prime Video.
    Las URLs del usuario suelen ser primevideo.com/detail/...
    pero el idioma español requiere primevideo.com/-/es/detail/...
    """
    if "/-/es/" not in url:
        url = url.replace("primevideo.com/", "primevideo.com/-/es/", 1)
    return url


def extract_title(html):
    """Extrae el título de la serie desde el HTML."""
    # Primero intentar desde el JSON de hidratación (más fiable)
    m = re.search(r'"parentTitle":"([^"]+)"', html)
    if m:
        return m.group(1)
    # Fallback: etiqueta <title>
    m = re.search(r"<title>Prime Video:\s*(.+?)</title>", html)
    if m:
        return m.group(1).strip()
    return "Título desconocido"


def search_in_html(html):
    """
    Busca los patrones de accesibilidad española en el HTML.
    Retorna lista con los tipos detectados.
    """
    detected = []
    # Normalizar espacios para no tener problemas con saltos de línea
    clean = re.sub(r"\s+", " ", html)

    # 1. Audiodescripción en Español (España)
    if re.search(
        r'Español\s*\(España\)\s*\[descripci[oó]n\s+de\s+audio\]',
        clean, re.IGNORECASE
    ):
        detected.append("Audiodescripción en Español (España)")

    # 2. Subtítulos CC en Español (España)
    if re.search(
        r'Español\s*\(España\)\s*\[CC\]',
        clean, re.IGNORECASE
    ):
        detected.append("Subtítulos CC en Español (España)")

    return detected


def fetch_url(url, session, retries=3, delay=5):
    """
    Descarga el HTML de una URL con reintentos.
    Usa requests en lugar de Playwright: el servidor ya devuelve el HTML
    completo con todos los datos de accesibilidad sin necesitar JavaScript.
    """
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"  [intento {attempt}/{retries}] Error: {e}")
            if attempt < retries:
                time.sleep(delay)
    return None


def add_rss_item(channel, title, url, detected_types):
    """Añade un nuevo item al canal RSS."""
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = url
    description = "Detectado: " + " | ".join(detected_types)
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

    for url in urls:
        print(f"Comprobando: {url}")
        try:
            norm_url = normalize_url(url)
            html = fetch_url(norm_url, session)

            if html is None:
                print("  ⚠️ No se pudo descargar la página.")
                pending_urls.append(url)
                continue

            detected_types = search_in_html(html)
            title = extract_title(html)

            if detected_types:
                print(f"  ✅ Encontrado en '{title}': {', '.join(detected_types)}")
                add_rss_item(channel, title, url, detected_types)
                found_any = True
                # NO añadir a pending: se elimina permanentemente
            else:
                print(f"  ❌ Sin accesibilidad española: '{title}'")
                pending_urls.append(url)

        except Exception as e:
            print(f"  ⚠️ Error inesperado: {e}")
            pending_urls.append(url)

        # Pausa breve entre peticiones para no estresar el servidor
        time.sleep(2)

    save_links(pending_urls)

    if found_any:
        tree.write(RSS_FILE, encoding="utf-8", xml_declaration=True)
        print("\nRSS actualizado.")
    else:
        print("\nSin novedades. RSS no modificado.")


if __name__ == "__main__":
    main()
