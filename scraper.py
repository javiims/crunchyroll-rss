import os
import time
import xml.etree.ElementTree as ET
from email.utils import formatdate
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

RSS_FILE = "feed.xml"
LINKS_FILE = "links.txt"

def load_links():
    if not os.path.exists(LINKS_FILE):
        return []
    with open(LINKS_FILE, 'r', encoding='utf-8') as f:
        # Lee los enlaces ignorando líneas en blanco
        return [line.strip() for line in f if line.strip()]

def save_links(links):
    # Sobrescribe el archivo solo con los enlaces que siguen pendientes
    with open(LINKS_FILE, 'w', encoding='utf-8') as f:
        for link in links:
            f.write(link + '\n')

def load_or_create_rss():
    if os.path.exists(RSS_FILE):
        tree = ET.parse(RSS_FILE)
        return tree, tree.getroot()
    else:
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "Novedades Castellano - Crunchyroll Prime Video"
        ET.SubElement(channel, "link").text = "https://www.primevideo.com"
        ET.SubElement(channel, "description").text = "Avisos de nuevas series con descripción de audio en Español (España)"
        return ET.ElementTree(rss), rss

def add_rss_item(channel, title, url, description):
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = url
    ET.SubElement(item, "description").text = description
    # Registra la hora exacta en la que se encontró la novedad
    ET.SubElement(item, "pubDate").text = formatdate(timeval=None, localtime=False, usegmt=True)

def main():
    urls_to_check = load_links()
    if not urls_to_check:
        return

    tree, rss = load_or_create_rss()
    channel = rss.find("channel")
    
    pending_urls = []
    found_new = False

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="es-ES", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()

        for url in urls_to_check:
            try:
                page.goto(url)
                time.sleep(5)
                
                # Obtenemos el texto de toda la página, incluyendo los bloques de detalles técnicos
                full_text = page.evaluate("document.body.innerText")
                
                # Buscamos el patrón exacto en texto plano.
                # Detectamos: "Español (España) [descripción de audio]" o variantes equivalentes
                # La regex busca "Español (España)" seguido de cualquier mención a audiodescripción
                is_audio_desc = bool(re.search(r'Español\s?\(España\).{0,50}?descrip[c|ç]i[ó|o]n de audio', full_text, re.IGNORECASE))
                
                # Detectamos audio normal en español que NO sea subtítulo
                is_audio_norm = bool(re.search(r'Español\s?\(España\)(?!\s*\[CC\])', full_text))

                if is_audio_desc or is_audio_norm:
                    title_str = page.title().replace("Prime Video:", "").strip()
                    
                    # Añadimos al RSS
                    add_rss_item(channel, title_str, url, f"Doblaje detectado: {'Audio Descriptivo' if is_audio_desc else 'Audio Estándar'}")
                    found_new = True
                else:
                    pending_urls.append(url)
                    
            except Exception:
                pending_urls.append(url)

        browser.close()

    save_links(pending_urls)
    if found_new:
        tree.write(RSS_FILE, encoding='utf-8', xml_declaration=True)

if __name__ == "__main__":
    main()
