import os
import re
import xml.etree.ElementTree as ET
from email.utils import formatdate
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

RSS_FILE = "feed.xml"
LINKS_FILE = "links.txt"

def load_links():
    if not os.path.exists(LINKS_FILE):
        return []
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def save_links(links):
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        for link in links:
            f.write(link + "\n")

def load_or_create_rss():
    if os.path.exists(RSS_FILE):
        tree = ET.parse(RSS_FILE)
        return tree, tree.getroot()

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Crunchyroll Prime Video - Novedades Accesibilidad"
    ET.SubElement(channel, "link").text = "https://www.primevideo.com"
    ET.SubElement(channel, "description").text = "Detección automática de audiodescripción y audio en Español (España)"
    
    return ET.ElementTree(rss), rss

def add_rss_item(channel, title, url, detected_type):
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = url
    ET.SubElement(item, "description").text = f"Detectado: {detected_type} en Español (España)"
    ET.SubElement(item, "pubDate").text = formatdate(timeval=None, localtime=False, usegmt=True)

def process_url(page, url):
    """Detecta el audio de forma infalible escaneando la lista de pistas interna."""
    page.goto(url, wait_until="networkidle", timeout=120000)
    html_content = page.content()
    
    # 1. Búsqueda exacta en la base de datos interna (JSON incrustado de Amazon)
    # Buscamos la lista "audioTracks":["..."] que Prime Video incluye en el código de la página.
    audio_match = re.search(r'"audioTracks"\s*:\s*\[(.*?)\]', html_content)
    if audio_match:
        audio_data = audio_match.group(1).lower()
        if "español (españa) [descripción de audio]" in audio_data:
            return "Audiodescripción"
        elif "español (españa)" in audio_data:
            return "Audio Estándar"

    # 2. Respaldo: Leer el texto visible de la sección de Audios
    # Por si Amazon cambia la estructura, aislamos estrictamente la sección "Idiomas de audio"
    try:
        text = page.locator("body").inner_text()
        text_clean = " ".join(text.split())
        
        if "Idiomas de audio" in text_clean:
            # Cortamos todo lo que haya después de "Subtítulos" para no mezclar audios con CC
            audio_section = text_clean.split("Idiomas de audio")[1].split("Subtítulos")[0].lower()
            if "español (españa) [descripción de audio]" in audio_section:
                return "Audiodescripción"
            elif "español (españa)" in audio_section:
                return "Audio Estándar"
    except Exception:
        pass
        
    return None

def extract_title(page):
    try:
        title = page.title().replace("Prime Video:", "").strip()
        return title if title else "Título desconocido"
    except Exception:
        return "Título desconocido"

def main():
    urls = load_links()
    if not urls:
        print("No hay enlaces pendientes.")
        return

    tree, rss = load_or_create_rss()
    channel = rss.find("channel")

    pending_urls = []
    found_any = False

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="es-ES",
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for url in urls:
            print(f"Comprobando: {url}")
            try:
                title = extract_title(page)
                detected_type = process_url(page, url)

                if detected_type:
                    print(f"Encontrado: {detected_type}")
                    add_rss_item(channel, title, url, detected_type)
                    found_any = True
                else:
                    print("Sin cambios.")
                    pending_urls.append(url)

            except Exception as e:
                print(f"Error: {e}")
                pending_urls.append(url)

        browser.close()

    save_links(pending_urls)

    if found_any:
        tree.write(RSS_FILE, encoding="utf-8", xml_declaration=True)
        print("RSS actualizado.")

    print(f"URLs pendientes: {len(pending_urls)}")

if __name__ == "__main__":
    main()
