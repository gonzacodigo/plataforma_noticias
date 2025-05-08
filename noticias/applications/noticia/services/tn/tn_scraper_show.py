# Importaciones necesarias
from datetime import datetime
from bs4 import BeautifulSoup
import requests
import time
from urllib.parse import urljoin
import pytz
from django.utils import timezone as django_timezone

# Importaciones de modelos de Django
from applications.noticia.models import Noticia, Categoria
from applications.medio.models import Medio

# Definición de cache para evitar múltiples solicitudes a Infobae
cache = {}
CACHE_DURATION = 300 # 5 minutos en segundos

def scrape_tn_show():
    # Verificar si existe información cacheada y si sigue vigente
    if 'tn_data' in cache and (time.time() - cache['tn_data']['timestamp'] < CACHE_DURATION):
        return cache['tn_data']['data']

    url = "https://tn.com.ar/show"
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
        noticias = soup.find_all('article', class_='card__container')


        # Obtener o crear el medio 'Infobae'
        medio, _ = Medio.objects.get_or_create(nombre='TN')

        for noticia in noticias:
            # Extraer el título
            title_tag = noticia.find('h2', class_="card__headline")
                    
            # Extraer link de la noticia
            link = noticia.find('a')
            link_href = link['href'] if link and 'href' in link.attrs else None

            # Validar que haya título y link
            if not title_tag or not link_href:
                continue

            title = title_tag.text.strip()

            # Evitar duplicar noticias
            if Noticia.objects.filter(titulo=title).exists():
                continue

            # Asegurarse que el link sea completo
            if not link_href.startswith('http'):
                link_href = urljoin("https://tn.com.ar/show/", link_href)

            # Categoría ESTATICA basada en el URL
            categoria_obj, _ = Categoria.objects.get_or_create(nombre='SHOW'.upper())


            # Obtener el contenido de la noticia completa
            try:
                article_response = session.get(link_href)
                article_response.raise_for_status()
            except requests.RequestException as e:
                print(f"Error al obtener artículo: {e}")
                continue

            # Parsear el HTML del artículo
            soup_article = BeautifulSoup(article_response.text, 'html.parser')
            article = soup_article.find_all('div', class_='col-content')
            if not article:
                continue

            for article in article:
                # Extraer el contenido de la noticia
                parrafos = soup_article.find_all('p', class_="paragraph")
                contenido = " ".join([p.get_text().strip() for p in parrafos]) if parrafos else ""
                # Extraer el párrafo (descripción)
                parrafo_tag = article.find('h2', class_='article__dropline font__body') if article else None
                            # Extraer imagen
                div_imagen = article.find('picture', class_="responsive-image")
                imagen_url = None  # Valor por defecto
                
                # Validar que haya contenido
                if not contenido.strip():
                    continue

                if div_imagen:
                    # Buscar la etiqueta img con la clase más específica
                    imagen = div_imagen.find('img', class_="width_full height_full article__lead-art-photo image_placeholder")
                    
                    if not imagen:
                        # Si no se encuentra, buscar otra clase alternativa
                        imagen = div_imagen.find('img', class_="image image_placeholder")

                    if imagen:
                        # Intentar obtener el src
                        if 'src' in imagen.attrs:
                            imagen_url = imagen['src']
                        elif 'data-interchange' in imagen.attrs:
                            data_interchange = imagen['data-interchange']
                            try:
                                # Extraer la URL del 'data-interchange'
                                imagen_url = data_interchange.split(',')[0].strip().split('[')[1]
                            except IndexError:
                                imagen_url = None  # Por si el formato no es el esperado         
                
            descripcion = parrafo_tag.text.strip() if parrafo_tag else ""
                
            # Extraer fecha de publicación
            date_tag = article.find('span', class_="time__value classNameFontTimeValue")
            date_text = date_tag.text.strip() if date_tag else None

            # Procesar fecha y hora
            fecha_hora_obj = None
            if date_text:
                try:
                    date_text = date_text.replace(",", "").replace("hs", "")  # Limpiar coma y "hs"
                    partes = date_text.split(" ")

                    if len(partes) >= 5:
                        dia = partes[0]
                        mes_texto = partes[2].lower()
                        anio = partes[3]
                        hora, minuto = partes[4].split(":")

                        # Diccionario de meses en español (formato largo)
                        meses = {
                            "enero": "01", "febrero": "02", "marzo": "03", "abril": "04", "mayo": "05",
                            "junio": "06", "julio": "07", "agosto": "08", "septiembre": "09", "octubre": "10",
                            "noviembre": "11", "diciembre": "12"
                        }

                        mes = meses.get(mes_texto, "01")
                        fecha_hora_str = f"{anio}-{mes}-{dia} {hora}:{minuto}"

                        # Crear objeto datetime con zona horaria Argentina
                        fecha_hora_obj = datetime.strptime(fecha_hora_str, "%Y-%m-%d %H:%M")
                        fecha_hora_obj = pytz.timezone("America/Argentina/Buenos_Aires").localize(fecha_hora_obj)

                except Exception as e:
                    print(f"Error procesando fecha: {e}")
                    fecha_hora_obj = django_timezone.now()
            else:
                fecha_hora_obj = django_timezone.now()

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
    cache['tn_data'] = {
        'data': resultado,
        'timestamp': time.time()
    }

    return resultado

