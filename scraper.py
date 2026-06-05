import re
import os
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

LINKS_FILE = "links.txt"
RSS_FILE = "feed.xml"


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


def extract_title(page):
    """Extrae el título de la página."""
    try:
        title = page.title()
        # Eliminar prefijo "Prime Video: "
        if title.startswith("Prime Video: "):
            title = title[len("Prime Video: "):]
        return title.strip()
    except Exception:
        return "Título desconocido"


def add_rss_item(channel, title, url, detected_types):
    """Añade un nuevo item al canal RSS."""
    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = url
    description = "Detectado: " + " | ".join(detected_types)
    ET.SubElement(item, "description").text = description
    pub_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    ET.SubElement(item, "pubDate").text = pub_date


def process_url(page, url):
    """
    Detecta accesibilidad española escaneando el código fuente crudo de la página.
    
    Busca específicamente:
    - "Español (España) [descripción de audio]" en la sección de audios
    - "Español (España) [CC]" en la sección de subtítulos
    
    Retorna una lista con los tipos detectados (puede ser vacía).
    """
    page.goto(url, wait_until="networkidle", timeout=120000)

    # Obtenemos el código fuente completo
    html_content = page.content()

    # Limpiamos el HTML para facilitar búsquedas (unimos líneas)
    clean_text = re.sub(r'\s+', ' ', html_content)

    detected = []

    # 1. Detectar Audiodescripción española
    # Busca la cadena exacta "Español (España) [descripción de audio]"
    # También acepta variantes con entidades HTML o codificación
    if re.search(
        r'Español\s*\(España\)\s*\[descripci[oó]n\s+de\s+audio\]',
        clean_text,
        re.IGNORECASE
    ):
        detected.append("Audiodescripción en Español (España)")

    # 2. Detectar Subtítulos CC en español de España
    # Busca la cadena exacta "Español (España) [CC]"
    if re.search(
        r'Español\s*\(España\)\s*\[CC\]',
        clean_text,
        re.IGNORECASE
    ):
        detected.append("Subtítulos CC en Español (España)")

    return detected


def main():
    urls = load_links()
    if not urls:
        print("No hay enlaces que comprobar.")
        return

    tree, rss = load_or_create_rss()
    channel = rss.find("channel")
    pending_urls = []
    found_any = False

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="es-ES",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        for url in urls:
            print(f"Comprobando: {url}")
            try:
                title = extract_title(page)

                # Procesamos y buscamos las dos pistas de accesibilidad
                detected_types = process_url(page, url)

                # Actualizar título tras cargar la página del producto
                title = extract_title(page)

                if detected_types:
                    print(f"  ✅ Encontrado: {', '.join(detected_types)}")
                    add_rss_item(channel, title, url, detected_types)
                    found_any = True
                    # NO añadir a pending: se elimina de la lista
                else:
                    print("  ❌ Sin cambios (accesibilidad española no detectada).")
                    pending_urls.append(url)

            except Exception as e:
                print(f"  ⚠️ Error en {url}: {e}")
                pending_urls.append(url)

        browser.close()

    save_links(pending_urls)

    if found_any:
        tree.write(RSS_FILE, encoding="utf-8", xml_declaration=True)
        print("RSS actualizado.")
    else:
        print("Sin novedades. RSS no modificado.")


if __name__ == "__main__":
    main()
