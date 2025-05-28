# Importaciones necesarias
from datetime import datetime
from bs4 import BeautifulSoup
import requests
import time
from urllib.parse import urljoin
from django.utils import timezone as django_timezone

# Importaciones de modelos de Django
from applications.noticia.models import Noticia, Categoria
from applications.medio.models import Medio

# Definición de cache para evitar múltiples solicitudes
cache = {}
CACHE_DURATION = 300  # 5 minutos en segundos

# Headers para simular navegador y evitar bloqueo
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'es-ES,es;q=0.9',
}

def scrape_clarin_general():
    if 'clarin_data' in cache and (time.time() - cache['clarin_data']['timestamp'] < CACHE_DURATION):
        return cache['clarin_data']['data']

    url = "https://www.clarin.com/"
    resultado = []

    with requests.Session() as session:
        session.headers.update(HEADERS)

        try:
            response = session.get(url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[ERROR] No se pudo acceder a Clarín: {e}")
            return {'error': 'No se pudo obtener las noticias de Clarín'}, 500

        soup = BeautifulSoup(response.text, 'html.parser')
        noticias = soup.find_all('article', class_='sc-17ef7676-0')
        medio, _ = Medio.objects.get_or_create(nombre='CLARIN')

        for noticia in noticias:
            title_tag = noticia.find('h2', class_="title")
            div_a = noticia.find('a', class_="sc-198398ff-0")
            link_href = div_a['href'] if div_a and 'href' in div_a.attrs else None

            if not title_tag or not link_href:
                continue

            title = title_tag.text.strip()
            if Noticia.objects.filter(titulo=title).exists():
                continue

            if not link_href.startswith('http'):
                link_href = urljoin(url, link_href)

            categoria_link = link_href.split("/")[3] if len(link_href.split("/")) > 3 else "General"
            if categoria_link.lower().startswith('watch'):
                continue

            categoria_nombre = categoria_link.upper()
            CATEGORIAS_VALIDAS = ['DEPORTES', 'INTERNACIONAL','POLICIALES', 'POLITICA', 'ECONOMIA', 'TECNO','MODA','CULTURA','AUTOS']
            if categoria_nombre not in CATEGORIAS_VALIDAS:
                categoria_nombre = 'GENERAL'
            categoria_obj, _ = Categoria.objects.get_or_create(nombre=categoria_nombre)

            # Imagen destacada
            div_imagen = noticia.find('picture')
            imagen_url = None
            if div_imagen:
                imagen = div_imagen.find('img')
                if imagen:
                    imagen_url = imagen.get('src') or imagen.get('data-src') or None
                    if not imagen_url and 'data-interchange' in imagen.attrs:
                        try:
                            data_interchange = imagen['data-interchange']
                            imagen_url = data_interchange.split(',')[0].strip().split('[')[1]
                        except Exception:
                            imagen_url = None

            # Obtener contenido del artículo completo
            try:
                article_response = session.get(link_href, timeout=10)
                article_response.raise_for_status()
            except requests.RequestException as e:
                print(f"[ERROR] No se pudo acceder al artículo: {e}")
                continue

            soup_article = BeautifulSoup(article_response.text, 'html.parser')
            contenido_divs = soup_article.find_all('div', class_="sc-80531b6b-0 chRIGJ container-text text-embed")
            contenido = "<br><br>".join([p.get_text().strip() for p in contenido_divs if p.get_text().strip()])

            if not contenido:
                continue

            parrafo_tag = soup_article.find('h2', class_='storySummary')
            descripcion = parrafo_tag.text.strip() if parrafo_tag else contenido[:200]

            # Fecha de publicación
            fecha_hora_obj = django_timezone.now()
            date_tag = soup_article.find('time', class_="createDate")
            if date_tag and date_tag.has_attr('datetime'):
                try:
                    fecha_iso = date_tag['datetime'].replace('Z', '+00:00')
                    fecha_hora_obj = datetime.fromisoformat(fecha_iso)
                    if django_timezone.is_naive(fecha_hora_obj):
                        fecha_hora_obj = django_timezone.make_aware(fecha_hora_obj, django_timezone.utc)
                except Exception as e:
                    print(f"[ERROR] No se pudo parsear la fecha: {e}")

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

            resultado.append({
                'id': noticia_obj.id,
                'title': title,
                'descripcion': descripcion,
                'contenido': contenido,
                'categoria': categoria_obj.nombre,
                'imageUrl': imagen_url,
                'url': link_href,
                'fecha': fecha_hora_obj.isoformat(),
            })

    cache['clarin_data'] = {
        'data': resultado,
        'timestamp': time.time()
    }

    return resultado

