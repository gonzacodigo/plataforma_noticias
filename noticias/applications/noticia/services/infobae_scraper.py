from bs4 import BeautifulSoup
import requests
import time
from urllib.parse import urljoin
from django.utils import timezone

from applications.noticia.models import Noticia
from applications.medio.models import Medio
from applications.categoria.models import Categoria

cache = {}
CACHE_DURATION = 300  # 5 minutos

def scrape_infobae():
    if 'infobae_data' in cache and (time.time() - cache['infobae_data']['timestamp'] < CACHE_DURATION):
        return cache['infobae_data']['data']

    url = "https://www.infobae.com/teleshow/"
    resultado = []

    with requests.Session() as session:
        try:
            response = session.get(url)
            response.raise_for_status()
        except requests.RequestException:
            return {'error': 'No se pudo obtener las noticias'}, 500

        soup = BeautifulSoup(response.text, 'html.parser')
        noticias = soup.find_all('a', class_='story-card-ctn')

        medio, _ = Medio.objects.get_or_create(nombre='Infobae')

        for noticia in noticias:
            title_tag = noticia.find('h2', class_="story-card-hl")
            parrafo_div = noticia.find('div', class_="story-card-info")
            parrafo_tag = parrafo_div.find('h3', class_='story-card-deck') if parrafo_div else None

            imagen = noticia.find('img', class_="global-image")
            imagen_url = imagen['src'] if imagen and 'src' in imagen.attrs else None
            link_href = noticia['href'] if noticia and 'href' in noticia.attrs else None

            if not title_tag or not link_href:
                continue

            title = title_tag.text.strip()
            descripcion = parrafo_tag.text.strip() if parrafo_tag else ""

            if Noticia.objects.filter(titulo=title).exists():
                continue

            if not link_href.startswith('http'):
                link_href = urljoin("https://www.infobae.com", link_href)

            # Categoría dinámica
            categoria_link = link_href.split("/")[3] if len(link_href.split("/")) > 3 else "General"
            categoria_obj, _ = Categoria.objects.get_or_create(nombre=categoria_link)

            # Extraer contenido
            try:
                article_response = session.get(link_href)
                article_response.raise_for_status()
            except requests.RequestException:
                continue

            soup_article = BeautifulSoup(article_response.text, 'html.parser')
            article = soup_article.find('article', class_='article')
            if not article:
                continue

            date_tag = article.find('span', class_="sharebar-article-date")
            date_text = date_tag.text.strip() if date_tag else None

            parrafos = soup_article.find_all('p', class_="paragraph")
            contenido = " ".join([p.get_text().strip() for p in parrafos]) if parrafos else ""

            noticia_obj = Noticia.objects.create(
                titulo=title,
                descripcion=descripcion[:300],
                fecha=timezone.now(),  # o parsear date_text
                portada=imagen_url or "",
                categoria=categoria_obj,
                medio=medio,
                visitas=0,
                url=link_href,
                contenido=contenido,  # <- acá
            )

            resultado.append({
                'id': noticia_obj.id,
                'title': title,
                'descripcion': descripcion,
                'contenido': contenido,
                'categoria': categoria_obj.nombre,
                'imageUrl': imagen_url,
                'url': link_href,
                'fecha': noticia_obj.fecha,
            })

    cache['infobae_data'] = {
        'data': resultado,
        'timestamp': time.time()
    }

    return resultado
