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

def scrape_telefe_general():
    # Verificar si existe información cacheada y si sigue vigente
    if 'telefe_data' in cache and (time.time() - cache['telefe_data']['timestamp'] < CACHE_DURATION):
        return cache['telefe_data']['data']

    url = "https://noticias.mitelefe.com/"
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
        noticias = soup.find_all('a', class_='e-card-link')



        # Obtener o crear el medio 'Infobae'
        medio, _ = Medio.objects.get_or_create(nombre='TELEFE')

        for noticia in noticias:
            # Extraer el título
            title_tag = noticia.find('h2', class_="e-card-title")

            # Extraer imagen
            div_imagen = noticia.find('div', class_="e-card-img-container")
            imagen_url = None

            if div_imagen:
                # Buscar la etiqueta img dentro del div
                imagen = div_imagen.find('img', class_="e-card-img")
                if imagen:
                    # Obtener el 'src' o intentar extraer desde 'data-interchange'
                    imagen_url = imagen['src'] if 'src' in imagen.attrs else None

                    if not imagen_url and 'data-interchange' in imagen.attrs:
                        # Extraer la URL del 'data-interchange'
                        data_interchange = imagen['data-interchange']
                        imagen_url = data_interchange.split(',')[
                            0].strip().split('[')[1]
                    
            # Extraer link de la noticia
            link_href = noticia['href'] if noticia and 'href' in noticia.attrs else None

            # Validar que haya título y link
            if not title_tag or not link_href:
                continue

            title = title_tag.text.strip()

            # Evitar duplicar noticias
            if Noticia.objects.filter(titulo=title).exists():
                continue

            # Asegurarse que el link sea completo
            if not link_href.startswith('http'):
                link_href = urljoin("https://noticias.mitelefe.com/", link_href)

            # Extraer categoría desde el link
            categoria_link = link_href.split("/")[3] if len(link_href.split("/")) > 3 else "General"

            # Ignorar si la categoría es tipo "watch"
            if categoria_link.lower().startswith('watch'):
                print('ENLACE IGNORADO PORQUE LA CATEGORIA ES WATCH')
                continue

            # Normalizar categoría
            categoria_nombre = categoria_link.upper()

            # Categorías permitidas explícitamente
            CATEGORIAS_VALIDAS = ['DEPORTES', 'INTERNACIONAL','POLICIALES', 'POLITICA', 'ECONOMIA']

            # Si no está en la lista permitida, asignar "GENERAL"
            if categoria_nombre not in CATEGORIAS_VALIDAS:
                categoria_nombre = 'GENERAL'

            # Crear o obtener la categoría
            categoria_obj, _ = Categoria.objects.get_or_create(nombre=categoria_nombre)


            # Obtener el contenido de la noticia completa
            try:
                article_response = session.get(link_href)
                article_response.raise_for_status()
            except requests.RequestException as e:
                print(f"Error al obtener artículo: {e}")
                continue

            # Parsear el HTML del artículo
            soup_article = BeautifulSoup(article_response.text, 'html.parser')
            article = soup_article.find_all('article', class_='b-post')
            
            if not article:
                continue

            for article in article:
                # Extraer el contenido de la noticia
                parrafos = soup_article.find_all('div', class_="e-post-text")
                contenido = "<br><br>".join([p.get_text().strip() for p in parrafos])
                # Extraer el párrafo (descripción)
                parrafo_tag = article.find('div', class_='e-post-subtitle') if article else None

                # Validar que haya contenido
                if not contenido.strip():
                    continue

            descripcion = parrafo_tag.text.strip() if parrafo_tag else ""

                
            # Extraer fecha de publicación
            date_tag = article.find('span', class_="e-post-time")
            date_text = date_tag.text.strip() if date_tag else None

            # Procesar fecha y hora
            fecha_hora_obj = None
            if date_text:
                try:
                    # Limpiar texto
                    date_text = date_text.replace(",", "").replace("hs", "").strip()
                    partes = date_text.split()

                    # Diccionario de meses en español
                    meses = {
                        "enero": "01", "febrero": "02", "marzo": "03", "abril": "04", "mayo": "05",
                        "junio": "06", "julio": "07", "agosto": "08", "septiembre": "09", "octubre": "10",
                        "noviembre": "11", "diciembre": "12"
                    }

                    if len(partes) >= 3:
                        dia = partes[0]
                        mes_texto = partes[1].lower()
                        anio = partes[2]
                        mes = meses.get(mes_texto, "01")

                        # Verificar si incluye hora
                        if len(partes) >= 4:
                            hora, minuto = partes[3].split(":")
                        else:
                            hora = "00"
                            minuto = "00"

                        fecha_hora_str = f"{anio}-{mes}-{dia} {hora}:{minuto}"

                        zona_ar = pytz.timezone("America/Argentina/Buenos_Aires")
                        fecha_hora_obj = datetime.strptime(fecha_hora_str, "%Y-%m-%d %H:%M")
                        fecha_hora_obj = zona_ar.localize(fecha_hora_obj)
                    else:
                        print(f"⚠️ Fecha incompleta: {date_text}")
                        fecha_hora_obj = django_timezone.now()

                except Exception as e:
                    print(f"Error procesando fecha: {e}")
                    fecha_hora_obj = django_timezone.now()
            else:
                print("No hay date_text, usando fecha actual.")
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
    cache['telefe_data'] = {
        'data': resultado,
        'timestamp': time.time()
    }

    return resultado

