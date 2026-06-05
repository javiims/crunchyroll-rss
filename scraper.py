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
    ).text = "Novedades Audiodescripción Crunchyroll Prime Video"

    ET.SubElement(
        channel,
        "link"
    ).text = "https://www.primevideo.com"

    ET.SubElement(
        channel,
        "description"
    ).text = "Series de Crunchyroll en Prime Video que reciben audiodescripción en castellano"

    return ET.ElementTree(rss), rss


def add_rss_item(channel, title, url):
    item = ET.SubElement(channel, "item")

    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = url

    ET.SubElement(
        item,
        "description"
    ).text = "Se ha detectado audiodescripción en Español (España)"

    ET.SubElement(
        item,
        "pubDate"
    ).text = formatdate(
        timeval=None,
        localtime=False,
        usegmt=True
    )


def audio_description_found(page):

    # Esperar carga principal
    page.wait_for_load_state("networkidle")

    # Scroll para forzar carga de detalles
    for _ in range(8):
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(1000)

    text = page.locator("body").inner_text().lower()

    patterns = [
        "Español (España) [descripción de audio]",
        "Español (España) [CC]"
    ]

    return any(pattern in text for pattern in patterns)


def main():

    urls = load_links()

    if not urls:
        print("No hay URLs pendientes")
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
            }
        )

        page = context.new_page()

        for url in urls:

            try:

                print(f"Comprobando: {url}")

                page.goto(
                    url,
                    timeout=120000,
                    wait_until="domcontentloaded"
                )

                if audio_description_found(page):

                    title = page.title()

                    title = (
                        title
                        .replace("Prime Video:", "")
                        .strip()
                    )

                    print(
                        f"Audiodescripción encontrada: {title}"
                    )

                    add_rss_item(
                        channel,
                        title,
                        url
                    )

                    found_any = True

                else:

                    print(
                        "No encontrada, seguirá en seguimiento"
                    )

                    pending_urls.append(url)

            except Exception as e:

                print(
                    f"Error en {url}: {e}"
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


if __name__ == "__main__":
    main()
