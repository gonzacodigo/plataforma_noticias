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

# Definición de cache para evitar múltiples solicitudes a Infobae
cache = {}
CACHE_DURATION = 300  # 5 minutos en segundos

def scrape_clarin_general():
    if 'clarin_data' in cache and (time.time() - cache['clarin_data']['timestamp'] < CACHE_DURATION):
        return cache['clarin_data']['data']

    url = "https://www.clarin.com/"
    resultado = []

    with requests.Session() as session:
        try:
            response = session.get(url)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error al obtener la página principal: {e}")
            return {'error': 'No se pudo obtener las noticias'}, 500

        soup = BeautifulSoup(response.text, 'html.parser')
        noticias = soup.find_all('article', class_='sc-17ef7676-0')

        medio, _ = Medio.objects.get_or_create(nombre='CLARIN')

        for noticia in noticias:
            title_tag = noticia.find('h2', class_="title")

            div_imagen = noticia.find('picture')
            imagen_url = None
            if div_imagen:
                imagen = div_imagen.find('img')
                if imagen:
                    imagen_url = imagen.get('src') or None
                    if not imagen_url and 'data-interchange' in imagen.attrs:
                        data_interchange = imagen['data-interchange']
                        imagen_url = data_interchange.split(',')[0].strip().split('[')[1]

            div_a = noticia.find('a', class_="sc-198398ff-0")
            link_href = div_a['href'] if div_a and 'href' in div_a.attrs else None

            if not title_tag or not link_href:
                continue

            title = title_tag.text.strip()
            if Noticia.objects.filter(titulo=title).exists():
                continue

            if not link_href.startswith('http'):
                link_href = urljoin("https://www.clarin.com/", link_href)

            categoria_link = link_href.split("/")[3] if len(link_href.split("/")) > 3 else "General"
            categoria_nombre = categoria_link.upper()
            categoria_obj, _ = Categoria.objects.get_or_create(nombre=categoria_nombre)

            try:
                article_response = session.get(link_href)
                article_response.raise_for_status()
            except requests.RequestException as e:
                print(f"Error al obtener artículo: {e}")
                continue

            soup_article = BeautifulSoup(article_response.text, 'html.parser')
            article = soup_article.find_all('article', class_='sc-85c09be5-2 bPYxwJ')
            if not article:
                continue

            for article in article:
                parrafos = soup_article.find_all('div', class_="sc-80531b6b-0 chRIGJ container-text text-embed")
                contenido = " ".join([p.get_text().strip() for p in parrafos]) if parrafos else ""

                parrafo_tag = article.find('h2', class_='storySummary') if article else None

                # ✅ Fecha desde el atributo datetime del <time>
                fecha_hora_obj = django_timezone.now()  # Valor por defecto
                date_tag = article.find('time', class_="createDate")
                if date_tag and date_tag.has_attr('datetime'):
                    try:
                        fecha_iso = date_tag['datetime'].replace('Z', '+00:00')  # UTC
                        fecha_hora_obj = datetime.fromisoformat(fecha_iso)
                        if django_timezone.is_naive(fecha_hora_obj):
                            fecha_hora_obj = django_timezone.make_aware(fecha_hora_obj, django_timezone.utc)
                    except Exception as e:
                        print(f"Error al parsear datetime ISO: {e}")
                        fecha_hora_obj = django_timezone.now()

                if not contenido.strip():
                    continue

                descripcion = parrafo_tag.text.strip() if parrafo_tag else ""

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

    cache['lanacion_data'] = {
        'data': resultado,
        'timestamp': time.time()
    }

    return resultado
