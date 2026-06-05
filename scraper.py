import os
import json
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
        return [
            line.strip()
            for line in f
            if line.strip()
        ]


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

    ET.SubElement(
        channel,
        "title"
    ).text = "Crunchyroll Prime Video - Novedades Accesibilidad"

    ET.SubElement(
        channel,
        "link"
    ).text = "https://www.primevideo.com"

    ET.SubElement(
        channel,
        "description"
    ).text = (
        "Detección automática de audiodescripción "
        "y subtítulos CC en Español (España)"
    )

    return ET.ElementTree(rss), rss


def add_rss_item(channel, title, url, detected_type):

    item = ET.SubElement(channel, "item")

    ET.SubElement(
        item,
        "title"
    ).text = title

    ET.SubElement(
        item,
        "link"
    ).text = url

    ET.SubElement(
        item,
        "description"
    ).text = (
        f"Detectado: {detected_type} "
        f"en Español (España)"
    )

    ET.SubElement(
        item,
        "pubDate"
    ).text = formatdate(
        timeval=None,
        localtime=False,
        usegmt=True
    )


def extract_hydration_json(page):

    selectors = [
        "#dv-web-page-hydration-data",
        "script#dv-web-page-hydration-data"
    ]

    for selector in selectors:

        try:

            locator = page.locator(selector)

            if locator.count() == 0:
                continue

            raw_json = locator.first.inner_text()

            if not raw_json.strip():
                continue

            return json.loads(raw_json)

        except Exception:
            continue

    return None


def find_spanish_accessibility(data):

    if not data:
        return None

    text = json.dumps(
        data,
        ensure_ascii=False
    ).lower()

    if "español (españa) [descripción de audio]" in text:
        return "Audiodescripción"

    if "español (españa) [cc]" in text:
        return "Subtítulos CC"

    return None


def extract_title(page):

    try:

        title = page.title()

        title = (
            title
            .replace("Prime Video:", "")
            .strip()
        )

        if title:
            return title

    except Exception:
        pass

    return "Título desconocido"


def process_url(page, url):

    page.goto(
        url,
        wait_until="networkidle",
        timeout=120000
    )

    data = extract_hydration_json(page)

    if not data:
        print("No se encontró JSON de hidratación")
        return None, None

    detected_type = find_spanish_accessibility(data)

    if not detected_type:
        return None, None

    title = extract_title(page)

    return title, detected_type


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

        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            locale="es-ES",
            viewport={
                "width": 1920,
                "height": 1080
            },
            user_agent=(
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/136.0.0.0 "
                "Safari/537.36"
            )
        )

        page = context.new_page()

        for url in urls:

            print(f"Comprobando: {url}")

            try:

                title, detected_type = process_url(
                    page,
                    url
                )

                if detected_type:

                    print(
                        f"Encontrado: {detected_type}"
                    )

                    add_rss_item(
                        channel,
                        title,
                        url,
                        detected_type
                    )

                    found_any = True

                    # IMPORTANTE:
                    # NO se añade a pending_urls,
                    # por lo que desaparece de links.txt

                else:

                    print(
                        "Sin cambios."
                    )

                    pending_urls.append(url)

            except Exception as e:

                print(
                    f"Error: {e}"
                )

                pending_urls.append(url)

        browser.close()

    save_links(pending_urls)

    if found_any:

        tree.write(
            RSS_FILE,
            encoding="utf-8",
            xml_declaration=True
        )

        print("RSS actualizado.")

    print(
        f"URLs pendientes: {len(pending_urls)}"
    )


if __name__ == "__main__":
    main()
