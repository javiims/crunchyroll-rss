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
        print("No hay enlaces pendientes en links.txt. Saliendo...", flush=True)
        return

    tree, rss = load_or_create_rss()
    channel = rss.find("channel")
    
    pending_urls = []
    found_new = False

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            locale="es-ES",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        page.set_default_timeout(45000)

        for url in urls_to_check:
            print(f"\nRevisando: {url}", flush=True)
            try:
                page.goto(url)
                time.sleep(4) # Pausa para asegurar que la web renderiza los idiomas
                
                content = page.content()
                
                # Buscamos exclusivamente la etiqueta de audio descriptivo
                if "Español (España) [descripción de audio]" in content:
                    title_str = page.title().replace("Prime Video:", "").strip()
                    if not title_str or title_str == "Prime Video": 
                        title_str = "Serie/Temporada en Prime Video"
                    
                    desc = f"¡Novedad! Se ha añadido el Audio Descriptivo en Castellano para: {title_str}."
                    add_rss_item(channel, title_str, url, desc)
                    
                    print(f"✅ ¡ENCONTRADO! Añadido al RSS y eliminado de la lista: {title_str}", flush=True)
                    found_new = True
                else:
                    print("❌ Aún no tiene audio descriptivo. Se mantiene en vigilancia.", flush=True)
                    pending_urls.append(url) # Se guarda para la próxima revisión
                    
            except Exception as e:
                print(f"⚠️ Error al cargar la página (se intentará en la siguiente ronda): {e}", flush=True)
                pending_urls.append(url)

        browser.close()

    # Guardamos la lista de enlaces actualizada (sin los que ya hemos detectado)
    save_links(pending_urls)
    
    # Solo actualizamos el feed.xml si ha habido novedades
    if found_new:
        tree.write(RSS_FILE, encoding='utf-8', xml_declaration=True)

if __name__ == "__main__":
    main()
