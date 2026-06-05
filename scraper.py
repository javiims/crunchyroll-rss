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


def search_in_html(html_content):
    """
    Busca los patrones de accesibilidad en el HTML crudo.
    Busca tanto en el DOM renderizado como en el JSON de hidratación embebido.
    Retorna lista de tipos detectados.
    """
    detected = []

    # Patrón 1: Audiodescripción en español de España
    # Busca la cadena exacta con variantes de codificación
    pattern_ad = r'Español\s*\(España\)\s*\[descripci[oó]n\s+de\s+audio\]'

    # Patrón 2: Subtítulos CC en español de España
    pattern_cc = r'Español\s*\(España\)\s*\[CC\]'

    # Búsqueda en todo el HTML (incluye DOM + JSON embebido)
    if re.search(pattern_ad, html_content, re.IGNORECASE):
        detected.append("Audiodescripción en Español (España)")

    if re.search(pattern_cc, html_content, re.IGNORECASE):
        detected.append("Subtítulos CC en Español (España)")

    return detected


def process_url(page, url):
    """
    Carga la URL y detecta accesibilidad española.

    Estrategia robusta:
    1. Carga la página completa (networkidle)
    2. Hace clic en la pestaña "Detalles" para forzar el renderizado de la sección
       que contiene los idiomas de audio y subtítulos
    3. Espera a que aparezca el contenedor de detalles
    4. Obtiene el HTML completo y busca los patrones
    5. Si no encuentra nada en el DOM, busca en el JSON de hidratación embebido (SSR)

    Retorna una lista con los tipos detectados (puede ser vacía).
    """
    page.goto(url, wait_until="networkidle", timeout=120000)

    # Intentar hacer clic en la pestaña "Detalles" para asegurar que
    # el contenido de idiomas y subtítulos está visible en el DOM
    try:
        details_tab = page.locator('[data-testid="btf-details-tab"]')
        details_tab.click(timeout=10000)
        # Esperar a que el contenido de detalles esté visible
        page.wait_for_selector('#tab-content-details', state='visible', timeout=10000)
        # Pausa breve para que React termine de renderizar
        page.wait_for_timeout(1000)
    except Exception:
        # Si no se puede clicar (por ejemplo, la pestaña no existe o ya está activa),
        # continuamos igualmente
        pass

    # Obtener el HTML completo (incluye SSR JSON + DOM renderizado)
    html_content = page.content()

    # Buscar patrones en el HTML completo
    detected = search_in_html(html_content)

    # Si no encontró nada, intentar buscar en el JSON de hidratación directamente
    # (el script id="dv-web-page-hydration-data" contiene los datos en SSR)
    if not detected:
        try:
            json_text = page.evaluate(
                """() => {
                    const el = document.getElementById('dv-web-page-hydration-data');
                    return el ? el.textContent : '';
                }"""
            )
            if json_text:
                detected = search_in_html(json_text)
        except Exception:
            pass

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
                # Procesar la URL (carga + clic en detalles + búsqueda)
                detected_types = process_url(page, url)

                # Obtener título después de cargar la página
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
