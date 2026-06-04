import requests
import re
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from email.utils import formatdate
import os

BASE_URL = "https://www.primevideo.com"
# Páginas base para extraer el catálogo de Crunchyroll
SEARCH_URLS = [
    "https://www.primevideo.com/storefront/channels?jic=20%7CEgxzdWJzY3JpcHRpb24%3D&benefitId=crunchyrolles",
    "https://www.primevideo.com/search/ref=atv_sr_sug_1?phrase=crunchyroll"
]
RSS_FILE = "feed.xml"

def load_or_create_rss():
    if os.path.exists(RSS_FILE):
        tree = ET.parse(RSS_FILE)
        return tree, tree.getroot()
    else:
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "Novedades Castellano - Crunchyroll en Prime Video"
        ET.SubElement(channel, "link").text = BASE_URL
        ET.SubElement(channel, "description").text = "Avisos de nuevos subtítulos [CC] y descripciones de audio en Español (España)"
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

def get_catalog_links(headers):
    links = set()
    for search_url in SEARCH_URLS:
        try:
            res = requests.get(search_url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a['href']
                if "/detail/" in href:
                    # Limpiar la URL para evitar duplicados
                    clean_url = BASE_URL + href.split('?')[0].split('ref=')[0]
                    links.add(clean_url)
        except Exception:
            pass
    return list(links)

def main():
    tree, rss = load_or_create_rss()
    channel = rss.find("channel")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept-Language": "es-ES,es;q=0.9"
    }
    
    # 1. Rastrear y obtener todas las URLs del catálogo disponibles
    series_urls = get_catalog_links(headers)
    
    # 2. Visitar cada serie y buscar los textos objetivo
    for url in series_urls:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                html = res.text
                has_cc = "Español (España) [CC]" in html
                has_audio = "Español (España) [descripción de audio]" in html
                
                if (has_cc or has_audio) and not item_exists(channel, url):
                    soup = BeautifulSoup(html, "html.parser")
                    title_tag = soup.find("title")
                    title = title_tag.text.replace("Prime Video: ", "") if title_tag else "Nueva Serie"
                    
                    desc = f"Detectado idioma castellano en {title}: "
                    if has_cc: desc += "Incluye Subtítulos [CC]. "
                    if has_audio: desc += "Incluye Audio descriptivo. "
                    
                    add_rss_item(channel, title, url, desc)
        except Exception:
            continue
            
    tree.write(RSS_FILE, encoding='utf-8', xml_declaration=True)

if __name__ == "__main__":
    main()
