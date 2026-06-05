import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import xml.etree.ElementTree as ET
from email.utils import formatdate
import os
import time

CHANNEL_URL = "https://www.primevideo.com/channel/bf569eea-cd6f-bcee-4f52-d9c08d36e02b/"
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
        
        # Ampliamos el timeout global para que no vuelva a cortarse a los 30 segundos
        page.set_default_timeout(60000)

        print("Accediendo a Prime Video...", flush=True)
        unique_links = set()

        for target_url in [CHANNEL_URL, SEARCH_URL]:
            try:
                page.goto(target_url)
                # Cambiamos "networkidle" por "domcontentloaded" para ignorar el ruido de fondo
                page.wait_for_load_state("domcontentloaded")
                time.sleep(8) # Pausa manual para permitir que React/JavaScript pinte las carátulas

                try:
                    page.click("input[name='accept']", timeout=5000)
                    time.sleep(2)
                except:
                    pass

                for _ in range(12):
                    page.evaluate("window.scrollBy(0, 1500)")
                    time.sleep(2)

                # Extracción clásica
                dom_links = page.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.href)")
                for link in dom_links:
                    if link and "/detail/" in link and "primevideo.com" in link:
                        part = link.split('/detail/')[1].split('/')[0]
                        unique_links.add(f"{BASE_URL}/detail/{part}/")

                # Extracción profunda
                html_content = page.content()
                regex_links = re.findall(r'/detail/[A-Z0-9]{10,30}/', html_content)
                for path in regex_links:
                    unique_links.add(f"{BASE_URL}{path}")

            except Exception as e:
                print(f"Aviso en carga inicial: {e}", flush=True)

        print(f"Se han encontrado {len(unique_links)} temporadas/series únicas. Comenzando escaneo de idiomas...", flush=True)

        for url in unique_links:
            try:
                page.goto(url)
                # Pausa estática en lugar de esperar a selectores específicos que cambian dinámicamente
                time.sleep(4)
                
                content = page.content()
                
                has_cc = "Español (España) [CC]" in content
                has_audio = "Español (España) [descripción de audio]" in content
                
                if (has_cc or has_audio) and not item_exists(channel, url):
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
