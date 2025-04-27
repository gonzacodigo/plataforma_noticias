# Importaciones necesarias
from datetime import datetime
from bs4 import BeautifulSoup
import requests
import time
from urllib.parse import urljoin
import pytz
from django.utils import timezone as django_timezone

# Importaciones de modelos de Django
from applications.noticia.models import Noticia
from applications.medio.models import Medio
from applications.categoria.models import Categoria

# Definición de cache para evitar múltiples solicitudes a Infobae
cache = {}
CACHE_DURATION = 300  # 5 minutos en segundos

def scrape_infobae():
    # Verificar si existe información cacheada y si sigue vigente
    if 'infobae_data' in cache and (time.time() - cache['infobae_data']['timestamp'] < CACHE_DURATION):
        return cache['infobae_data']['data']

    url = "https://www.infobae.com/teleshow/"
    resultado = []

    with requests.Session() as session:
        try:
            response = session.get(url)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error al obtener la página principal: {e}")
            return {'error': 'No se pudo obtener las noticias'}, 500

        # Parsear el HTML de la página
        soup = BeautifulSoup(response.text, 'html.parser')
        noticias = soup.find_all('a', class_='story-card-ctn')

        # Obtener o crear el medio 'Infobae'
        medio, _ = Medio.objects.get_or_create(nombre='Infobae')

        for noticia in noticias:
            # Extraer el título
            title_tag = noticia.find('h2', class_="story-card-hl")
            # Extraer el párrafo (descripción)
            parrafo_div = noticia.find('div', class_="story-card-info")
            parrafo_tag = parrafo_div.find('h3', class_='story-card-deck') if parrafo_div else None
            # Extraer imagen
            imagen = noticia.find('img', class_="global-image")
            imagen_url = imagen['src'] if imagen and 'src' in imagen.attrs else None
            # Extraer link de la noticia
            link_href = noticia['href'] if noticia and 'href' in noticia.attrs else None

            # Validar que haya título y link
            if not title_tag or not link_href:
                continue

            title = title_tag.text.strip()
            descripcion = parrafo_tag.text.strip() if parrafo_tag else ""

            # Evitar duplicar noticias
            if Noticia.objects.filter(titulo=title).exists():
                continue

            # Asegurarse que el link sea completo
            if not link_href.startswith('http'):
                link_href = urljoin("https://www.infobae.com", link_href)

            # Categoría dinámica basada en el URL
            categoria_link = link_href.split("/")[3] if len(link_href.split("/")) > 3 else "General"
            categoria_obj, _ = Categoria.objects.get_or_create(nombre=categoria_link)

            # Obtener el contenido de la noticia completa
            try:
                article_response = session.get(link_href)
                article_response.raise_for_status()
            except requests.RequestException as e:
                print(f"Error al obtener artículo: {e}")
                continue

            # Parsear el HTML del artículo
            soup_article = BeautifulSoup(article_response.text, 'html.parser')
            article = soup_article.find('article', class_='article')
            if not article:
                continue

            # Extraer fecha de publicación
            date_tag = article.find('span', class_="sharebar-article-date")
            date_text = date_tag.text.strip() if date_tag else None

            # Limpiar la coma en la fecha
            if date_text:
                date_text = date_text.replace(",", "")

            # Procesar fecha y hora
            fecha_hora_obj = None
            if date_text:
                try:
                    partes = date_text.split(" ")
                    if len(partes) >= 5:
                        dia = partes[0]
                        mes_texto = partes[1]
                        anio = partes[2]
                        hora_minuto = partes[3]
                        ampm = partes[4]

                        # Diccionario de meses en español
                        meses = {
                            "Ene": "01", "Feb": "02", "Mar": "03", "Abr": "04", "May": "05",
                            "Jun": "06", "Jul": "07", "Ago": "08", "Sep": "09", "Oct": "10",
                            "Nov": "11", "Dic": "12"
                        }
                        # Buscar el número de mes
                        mes = meses.get(mes_texto, "01")

                        # Armar fecha
                        fecha_str = f"{anio}-{mes}-{dia}"

                        # Ajustar hora según AM/PM
                        hora, minuto = hora_minuto.split(":")
                        if ampm.lower() == "p.m." and int(hora) != 12:
                            hora = str(int(hora) + 12)
                        elif ampm.lower() == "a.m." and int(hora) == 12:
                            hora = "00"

                        # Armar hora
                        hora_str = f"{hora}:{minuto}"
                        fecha_hora_str = f"{fecha_str} {hora_str}"

                        # Crear objeto datetime con timezone de Buenos Aires
                        fecha_hora_obj = datetime.strptime(fecha_hora_str, "%Y-%m-%d %H:%M")
                        fecha_hora_obj = pytz.timezone("America/Argentina/Buenos_Aires").localize(fecha_hora_obj)

                except Exception as e:
                    print(f"Error procesando fecha: {e}")
                    fecha_hora_obj = django_timezone.now()  # Si falla algo, se usa la fecha y hora actuales
            else:
                fecha_hora_obj = django_timezone.now()

            # Extraer el contenido de la noticia
            parrafos = soup_article.find_all('p', class_="paragraph")
            contenido = " ".join([p.get_text().strip() for p in parrafos]) if parrafos else ""

            # Crear el objeto Noticia en la base de datos
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

            # Agregar noticia a la respuesta
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

    # Guardar resultados en cache
    cache['infobae_data'] = {
        'data': resultado,
        'timestamp': time.time()
    }

    return resultado
