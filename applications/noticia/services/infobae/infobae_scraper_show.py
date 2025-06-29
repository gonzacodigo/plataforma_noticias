from datetime import datetime
from bs4 import BeautifulSoup
import requests
import time
from urllib.parse import urljoin
import pytz
from django.utils import timezone as django_timezone

from applications.noticia.models import Noticia, Categoria, NoticiaImagen
from applications.medio.models import Medio

# Definición de cache para evitar múltiples solicitudes a Infobae
cache = {}
CACHE_DURATION = 300  # 5 minutos en segundos


def extraer_imagenes_articulo(soup_article, imagen_fallback=None):
    """Devuelve una lista de URLs de imágenes del artículo."""
    urls_imagenes = []

    article_tag = soup_article.find('div', class_='body-article')
    if not article_tag:
        return [imagen_fallback] if imagen_fallback else []

    imagenes = article_tag.find_all('img')
    for img in imagenes:
        src = img.get('src') or img.get('data-src')
        if src and src.startswith('http'):
            urls_imagenes.append(src)

    if not urls_imagenes and imagen_fallback:
        urls_imagenes = [imagen_fallback]

    return urls_imagenes


def scrape_infobae_show():
    # Verificar si existe información cacheada y si sigue vigente
    if 'infobae_data' in cache and (time.time() - cache['infobae_data']['timestamp'] < CACHE_DURATION):
        return cache['infobae_data']['data']

    url = "https://www.infobae.com/teleshow/"
    resultado = []

    with requests.Session() as session:
        try:
            response = session.get(url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error al obtener la página principal: {e}")
            return {'error': 'No se pudo obtener las noticias'}, 500

        soup = BeautifulSoup(response.text, 'html.parser')
        noticias = soup.find_all('a', class_='story-card-ctn')

        medio, _ = Medio.objects.get_or_create(nombre='INFOBAE')

        for noticia in noticias:
            title_tag = noticia.find('h2', class_="story-card-hl")
            imagen = noticia.find('img', class_="global-image")
            imagen_url = imagen['src'] if imagen and 'src' in imagen.attrs else None
            link_href = noticia['href'] if noticia and 'href' in noticia.attrs else None

            if not title_tag or not link_href:
                continue

            title = title_tag.text.strip()

            if Noticia.objects.filter(titulo=title).exists():
                continue

            if not link_href.startswith('http'):
                link_href = urljoin("https://www.infobae.com", link_href)

            categoria_link = link_href.split("/")[3] if len(link_href.split("/")) > 3 else "General"
            categoria_nombre = categoria_link.upper()

            if categoria_nombre == 'TELESHOW':
                categoria_nombre = 'ESPECTACULOS'

            if categoria_link.lower().startswith('watch'):
                continue

            CATEGORIAS_VALIDAS = ['ESPECTACULOS', 'DEPORTES', 'INTERNACIONAL', 'POLICIALES', 'POLITICA', 'ECONOMIA']
            if categoria_nombre not in CATEGORIAS_VALIDAS:
                categoria_nombre = 'GENERAL'

            categoria_obj, _ = Categoria.objects.get_or_create(nombre=categoria_nombre)

            # Obtener el contenido del artículo
            try:
                article_response = session.get(link_href, timeout=10)
                article_response.raise_for_status()
            except requests.RequestException as e:
                print(f"Error al obtener artículo: {e}")
                continue

            soup_article = BeautifulSoup(article_response.text, 'html.parser')
            article_header = soup_article.find('div', class_='article-header')
            article = soup_article.find('div', class_='body-article')
            if not article:
                continue

            parrafo_tag = article_header.find('h2', class_='article-subheadline text_align_left') if article_header else None
            descripcion = parrafo_tag.text.strip() if parrafo_tag else ""

            # Fecha
            date_tag = article.find('span', class_="sharebar-article-date")
            date_text = date_tag.text.strip().replace(",", "") if date_tag else None
            fecha_hora_obj = django_timezone.now()

            if date_text:
                try:
                    partes = date_text.split(" ")
                    if len(partes) >= 5:
                        dia = partes[0]
                        mes_texto = partes[1]
                        anio = partes[2]
                        hora_minuto = partes[3]
                        ampm = partes[4]

                        meses = {
                            "Ene": "01", "Feb": "02", "Mar": "03", "Abr": "04", "May": "05",
                            "Jun": "06", "Jul": "07", "Ago": "08", "Sep": "09", "Oct": "10",
                            "Nov": "11", "Dic": "12"
                        }
                        mes = meses.get(mes_texto, "01")
                        fecha_str = f"{anio}-{mes}-{dia}"
                        hora, minuto = hora_minuto.split(":")

                        if ampm.lower() == "p.m." and int(hora) != 12:
                            hora = str(int(hora) + 12)
                        elif ampm.lower() == "a.m." and int(hora) == 12:
                            hora = "00"

                        hora_str = f"{hora}:{minuto}"
                        fecha_hora_str = f"{fecha_str} {hora_str}"

                        fecha_hora_obj = datetime.strptime(fecha_hora_str, "%Y-%m-%d %H:%M")
                        fecha_hora_obj = pytz.timezone("America/Argentina/Buenos_Aires").localize(fecha_hora_obj)
                except Exception as e:
                    print(f"Error procesando fecha: {e}")

            # Contenido
            parrafos = soup_article.find_all('p', class_="paragraph")
            contenido = "<br><br>".join([p.get_text().strip() for p in parrafos])

            if not contenido.strip():
                continue

            noticia_obj = Noticia.objects.create(
                titulo=title,
                descripcion=descripcion[:300],
                fecha=fecha_hora_obj,
                portada=imagen_url or "",
                categoria=categoria_obj,
                medio=medio,
                visitas=0,
                url=link_href,
                contenido=contenido,
            )

            # Extraer imágenes internas
            urls_imagenes = extraer_imagenes_articulo(soup_article, imagen_url)

            for url_img in urls_imagenes:
                if url_img and url_img != imagen_url:
                    NoticiaImagen.objects.create(noticia=noticia_obj, url=url_img)

            resultado.append({
                'id': noticia_obj.id,
                'title': title,
                'descripcion': descripcion,
                'contenido': contenido,
                'categoria': categoria_obj.nombre,
                'imageUrl': imagen_url,
                'urls_imagenes': urls_imagenes,
                'url': link_href,
                'fecha': fecha_hora_obj.isoformat(),
            })

    cache['infobae_data'] = {
        'data': resultado,
        'timestamp': time.time()
    }

    return resultado
