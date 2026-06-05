from playwright.sync_api import sync_playwright
import xml.etree.ElementTree as ET
from email.utils import formatdate
import os
import time

CHANNEL_URL = "https://www.primevideo.com/channel/bf569eea-cd6f-bcee-4f52-d9c08d36e02b/"
BASE_URL = "https://www.primevideo.com"
RSS_FILE = "feed.xml"

def load_or_create_rss():
    if os.path.exists(RSS_FILE):
        tree = ET.parse(RSS_FILE)
        return tree, tree.getroot()
    else:
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "Novedades Castellano - Crunchyroll Prime Video"
        ET.SubElement(channel, "link").text = CHANNEL_URL
        ET.SubElement(channel, "description").text = "Avisos de nuevas series con subtítulos [CC] o descripción de audio en Español (España)"
        return ET.ElementTree(rss), rss

def item_exists(channel, url):
    for item in channel.findall('item'):
        link = item.find('link')
        if link is not None and url in link.text:
            return True
    return False

def add_rss_item(channel, title, url, description):
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = url
    ET.SubElement(item, "description").text = description
    ET.SubElement(item, "pubDate").text = formatdate(timeval=None, localtime=False, usegmt=True)

def main():
    tree, rss = load_or_create_rss()
    channel = rss.find("channel")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Camuflar la automatización simulando ser Google Chrome en un Windows 10 con monitor 1080p
        context = browser.new_context(
            locale="es-ES",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        # Usar flush=True en los print asegura que el log de GitHub se actualice en tiempo real
        print("Accediendo al canal de Crunchyroll en Prime Video...", flush=True)
        page.goto(CHANNEL_URL, timeout=60000)
        
        # Esperar a que la página termine de descargar los scripts iniciales y dar 5 segundos de margen extra
        page.wait_for_load_state("networkidle")
        time.sleep(5)

        print("Haciendo scroll para cargar el catálogo completo...", flush=True)
        for _ in range(15):
            page.evaluate("window.scrollBy(0, 1500)")
            time.sleep(2)

        print("Extrayendo enlaces de la página...", flush=True)
        # Extraer absolutamente todos los enlaces renderizados
        links = page.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.href)")

        unique_links = set()
        for link in links:
            # Filtrar solo aquellos que lleven a los detalles de una serie/temporada
            if link and ("/detail/" in link or "/dp/" in link) and "primevideo.com" in link:
                clean_url = link.split('?')[0].split('ref=')[0]
                unique_links.add(clean_url)

        print(f"Se han encontrado {len(unique_links)} temporadas/series únicas. Comenzando revisión...", flush=True)

        for url in unique_links:
            try:
                page.goto(url, timeout=45000)
                page.wait_for_selector("body", timeout=15000)
                time.sleep(1) # Pausa para asegurar que los elementos del DOM están listos
                
                content = page.content()
                
                # Buscar cualquiera de las dos variaciones que indicaste
                has_cc = "Español (España) [CC]" in content
                has_audio = "Español (España) [descripción de audio]" in content
                
                if (has_cc or has_audio) and not item_exists(channel, url):
                    title_str = page.title().replace("Prime Video: ", "").strip()
                    if not title_str:
                        title_str = "Serie/Temporada de Crunchyroll"
                        
                    desc = f"¡Novedad! Detectado idioma en {title_str}. "
                    if has_cc: desc += "Incluye Subtítulos [CC]. "
                    if has_audio: desc += "Incluye Audio descriptivo."
                    
                    add_rss_item(channel, title_str, url, desc)
                    print(f"NUEVO AÑADIDO AL RSS: {title_str} - {url}", flush=True)
            except Exception:
                continue

        browser.close()
            
    tree.write(RSS_FILE, encoding='utf-8', xml_declaration=True)

if __name__ == "__main__":
    main()
