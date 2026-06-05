def process_url(page, url):
    """Detecta el audio escaneando el código fuente crudo de la página."""
    page.goto(url, wait_until="networkidle", timeout=120000)
    
    # Obtenemos el código fuente completo (HTML crudo)
    # Esto es mucho más fiable que innerText porque no depende de cómo el CSS muestre el texto
    html_content = page.content()
    
    # Limpiamos el HTML para que sea más fácil de procesar por regex (quitamos saltos de línea y tags de estilo)
    # Esto une el texto para que las frases no se rompan
    clean_text = re.sub(r'\s+', ' ', html_content)

    # 1. Detectar Audiodescripción
    # Busca 'Español (España)' seguido de 'descripción de audio' con hasta 100 caracteres de margen
    # (por si hay etiquetas <span>, <div> o espacios entre medio)
    is_audio_desc = bool(re.search(r'Español\s?\(España\).{0,100}?descrip[c|ç]i[ó|o]n\s+de\s+audio', clean_text, re.IGNORECASE))
    
    # 2. Detectar Audio Normal (sin ser CC)
    # Buscamos 'Español (España)' asegurándonos de que no le sigue inmediatamente el [CC]
    # Esto es más seguro que usar split()
    has_spanish = "Español (España)" in html_content
    is_cc = "[CC]" in html_content # Comprobamos si existen subtítulos CC
    
    is_audio_norm = has_spanish and not is_cc

    if is_audio_desc:
        return "Audiodescripción"
    elif is_audio_norm:
        return "Audio Estándar"
            
    return None

def main():
    urls = load_links()
    if not urls:
        return

    tree, rss = load_or_create_rss()
    channel = rss.find("channel")
    pending_urls = []
    found_any = False

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="es-ES",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for url in urls:
            print(f"Comprobando: {url}")
            try:
                # Obtenemos el título antes de procesar
                page.goto(url, wait_until="networkidle")
                title = extract_title(page)
                
                # Procesamos con la nueva lógica de escaneo HTML
                detected_type = process_url(page, url)

                if detected_type:
                    print(f"✅ Encontrado: {detected_type}")
                    add_rss_item(channel, title, url, detected_type)
                    found_any = True
                else:
                    print("❌ Sin cambios (Audio no detectado).")
                    pending_urls.append(url)
            except Exception as e:
                print(f"⚠️ Error en {url}: {e}")
                pending_urls.append(url)

        browser.close()

    save_links(pending_urls)
    if found_any:
        tree.write(RSS_FILE, encoding="utf-8", xml_declaration=True)
        print("RSS actualizado.")
