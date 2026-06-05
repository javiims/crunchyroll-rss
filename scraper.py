import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import xml.etree.ElementTree as ET
from email.utils import formatdate
import os
import time

# Volvemos a usar la URL de búsqueda porque Amazon no la bloquea en servidores
SEARCH_URL = "https://www.primevideo.com/search/ref=atv_sr_sug_1?phrase=crunchyroll"
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
        ET.SubElement(channel, "link").text = "https://www.primevideo.com/channel/bf569eea-cd6f-bcee-4f52-d9c08d36e02b/"
        ET.SubElement(channel, "description").text = "Avisos de nuevas series con subtítulos [CC] o descripción de audio en Español (España)"
        return ET.ElementTree(rss), rss

def get_known_urls(channel):
    urls = set()
    for item in channel.findall('item'):
        link = item.find('link')
        if link is not None and link.text:
            urls.add(link.text)
    return urls

def add_rss_item(channel, title, url, description):
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = url
    ET.SubElement(item, "description").text = description
    ET.SubElement(item, "pubDate").text = formatdate(timeval=None, localtime=False, usegmt=True)

def main():
    tree, rss = load_or_create_rss()
    channel = rss.find("channel")
    known_urls = get_known_urls(channel)

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = browser.new_context(
            locale="es-ES",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        print("Buscando catálogo a través del buscador general para evitar el bloqueo...", flush=True)
        unique_ids = set()

        try:
            page.goto(SEARCH_URL)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(8) 

            try:
                page.locator("input[name='accept'], button:has-text('Aceptar')").first.click(timeout=5000)
                time.sleep(2)
            except:
                pass

            for _ in range(15):
                page.mouse.wheel(0, 1500)
                time.sleep(1.5)

            html_content = page.content()

            dom_links = page.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.href || '')")
            for link in dom_links:
                match = re.search(r'/(?:detail|dp)/([A-Z0-9]{10,30})', link)
                if match: unique_ids.add(match.group(1))

            regex_paths = re.findall(r'/(?:detail|dp)/([A-Z0-9]{10,30})', html_content)
            for id_ in regex_paths: unique_ids.add(id_)

            json_ids = re.findall(r'"titleId":"([A-Z0-9]{10,30})"', html_content)
            for id_ in json_ids: unique_ids.add(id_)

        except Exception as e:
            print(f"Aviso en carga: {e}", flush=True)

        print(f"Se han encontrado {len(unique_ids)} resultados. Filtrando externos y conocidos...", flush=True)

        for video_id in unique_ids:
            url = f"{BASE_URL}/detail/{video_id}/"
            
            if url in known_urls:
                continue

            try:
                page.goto(url)
                time.sleep(3)
                
                content = page.content()
                
                # FILTRO ESTRICTO: Si la página de la serie no dice "Crunchyroll", la saltamos.
                if "crunchyroll" not in content.lower():
                    continue
                
                has_cc = "Español (España) [CC]" in content
                has_audio = "Español (España) [descripción de audio]" in content
                
                if has_cc or has_audio:
                    title_str = page.title().replace("Prime Video:", "").strip()
                    if not title_str or title_str == "Prime Video": 
                        title_str = "Serie de Crunchyroll"
                    
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
