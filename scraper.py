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
        ET.SubElement(channel, "title").text = "Novedades Castellano [CC] - Crunchyroll"
        ET.SubElement(channel, "link").text = CHANNEL_URL
        ET.SubElement(channel, "description").text = "Avisos de nuevas temporadas con subtítulos Español (España) [CC]"
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
        # Iniciamos un navegador Chromium (Chrome) invisible
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="es-ES")
        page = context.new_page()

        print("Accediendo al canal de Crunchyroll en Prime Video...")
        page.goto(CHANNEL_URL, timeout=60000)
        page.wait_for_load_state("networkidle")

        # Hacer scroll múltiple para forzar la carga de todas las filas y series
        print("Haciendo scroll para cargar el catálogo completo...")
        for _ in range(15):
            page.evaluate("window.scrollBy(0, 1500)")
            time.sleep(2) # Esperar a que carguen las carátulas

        # Extraer todos los enlaces de detalles de series/temporadas
        links = page.locator("a[href*='/detail/']").evaluate_all(
            "elements => elements.map(e => e.getAttribute('href'))"
        )

        unique_links = set()
        for link in links:
            if link:
                # Limpiamos la URL para quedarnos con el identificador único
                clean_url = BASE_URL + link.split('?')[0].split('ref=')[0]
                unique_links.add(clean_url)

        print(f"Se han encontrado {len(unique_links)} temporadas/series únicas. Comenzando revisión...")

        # Visitar cada serie y buscar el texto exacto
        for url in unique_links:
            try:
                page.goto(url, timeout=45000)
                # Esperamos a que cargue el cuerpo de la página
                page.wait_for_selector("body", timeout=15000)
                
                # Leemos todo el contenido de la web cargada
                content = page.content()
                
                if "Español (España) [CC]" in content and not item_exists(channel, url):
                    title = page.title().replace("Prime Video: ", "")
                    desc = f"¡Novedad! Detectados subtítulos Español (España) [CC] en: {title}"
                    
                    add_rss_item(channel, title, url, desc)
                    print(f"NUEVO AÑADIDO AL RSS: {title} - {url}")
            except Exception as e:
                print(f"Omitiendo {url} debido a un error de carga.")
                continue

        browser.close()
            
    # Guardamos el archivo RSS modificado
    tree.write(RSS_FILE, encoding='utf-8', xml_declaration=True)

if __name__ == "__main__":
    main()
