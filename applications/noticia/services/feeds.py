"""Medios que se descubren por RSS (o sitemap de noticias) y se leen completos.

El canal da la lista de notas nuevas (título, fecha, foto y enlace), que casi
nunca cambia de formato. De cada nota nueva se baja la página y se extrae el
texto. Si no se puede (nota exclusiva para suscriptores, página rota), se
guarda solo el resumen marcado como ``solo_tendencias``: alimenta las
tendencias, no aparece en el listado y su tarjeta lleva al medio original.
"""
import json
import logging
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from applications.medio.models import Medio
from applications.noticia.models import Noticia, ScrapeRun
from .engine import (
    ScrapeError,
    allowed_url,
    article_metadata,
    categoria_por_url,
    fetch_bytes,
    fetch_html,
    image_url,
    parse_date,
    persist_article,
    source_lock,
)

logger = logging.getLogger(__name__)

FEEDS = {
    "lanacion": {
        "medio": "LA NACION",
        "urls": ("https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml",),
        # Espectáculos ya se baja completo con el adaptador lanacion_show.
        "excluir": ("/espectaculos/",),
    },
    "perfil": {
        "medio": "PERFIL",
        "urls": ("https://www.perfil.com/feed",),
        # perfil.com y sus revistas (Caras, Exitoína, 442) usan estructuras distintas.
        "parrafos": (".news-body p", ".news__body p", ".article-body p", "article p"),
    },
    "pagina12": {
        "medio": "PAGINA 12",
        "urls": ("https://www.pagina12.com.ar/arc/outboundfeeds/breakingnews-short.xml",),
    },
    "c5n": {
        "medio": "C5N",
        "urls": (
            "https://www.c5n.com/rss/pages/ultimas-noticias.xml",
            "https://www.c5n.com/rss/pages/home.xml",
        ),
        "parrafos": ".article-body p",
    },
    "ambito": {
        "medio": "AMBITO",
        "urls": (
            "https://www.ambito.com/rss/pages/ultimas-noticias.xml",
            "https://www.ambito.com/rss/pages/home.xml",
        ),
        "parrafos": ".article-body p",
    },
}
# Con menos texto que esto la nota se guarda como resumen (solo tendencias).
TEXTO_MINIMO = 200
PARRAFO_MINIMO = 30

NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
    "media": "http://search.yahoo.com/mrss/",
}
SECCIONES = (
    (("espectacul", "show", "television", "famosos", "musica", "cine", "entretenimiento", "corazon"), "ESPECTACULOS"),
    (("deporte", "futbol", "automovilismo"), "DEPORTES"),
    (("econom", "finanzas", "negocios", "mercados"), "ECONOMIA"),
    (("politica", "el pais"), "POLITICA"),
    (("mundo", "internacional"), "INTERNACIONAL"),
    (("policial", "seguridad"), "POLICIALES"),
)


def _texto(elemento):
    return (elemento.text or "").strip() if elemento is not None else ""


def _normalizar(valor):
    valor = unicodedata.normalize("NFKD", str(valor or "").lower())
    return "".join(c for c in valor if not unicodedata.combining(c))


def _limpiar_html(valor):
    if not valor:
        return ""
    soup = BeautifulSoup(valor, "html.parser")
    for tag in soup.find_all(["ul", "ol", "script", "style", "figure"]):
        tag.decompose()  # C5N agrega listas de notas relacionadas.
    return " ".join(soup.get_text(" ", strip=True).split())


def categoria_por_seccion(seccion):
    nombre = _normalizar(seccion)
    for claves, categoria in SECCIONES:
        if any(clave in nombre for clave in claves):
            return categoria
    return "GENERAL"


def leer_feed(contenido):
    """Convierte un RSS o un sitemap de noticias en una lista de notas."""
    raiz = ET.fromstring(contenido)
    notas = []
    if raiz.tag.endswith("urlset"):
        for url in raiz.findall("sm:url", NS):
            notas.append(
                {
                    "titulo": _texto(url.find("news:news/news:title", NS)),
                    "url": _texto(url.find("sm:loc", NS)),
                    "descripcion": "",
                    "fecha": _texto(url.find("news:news/news:publication_date", NS)),
                    "imagen": _texto(url.find("image:image/image:loc", NS)),
                    "seccion": "",
                }
            )
        return notas
    for item in raiz.iter("item"):
        imagen = ""
        for tag in ("media:content", "media:thumbnail"):
            encontrado = item.find(tag, NS)
            if encontrado is not None and encontrado.get("url"):
                imagen = encontrado.get("url")
                break
        enclosure = item.find("enclosure")
        if not imagen and enclosure is not None and (enclosure.get("type") or "").startswith("image/"):
            imagen = enclosure.get("url", "")
        notas.append(
            {
                "titulo": _limpiar_html(_texto(item.find("title"))),
                "url": _texto(item.find("link")) or _texto(item.find("guid")),
                "descripcion": _limpiar_html(_texto(item.find("description"))),
                "fecha": _texto(item.find("pubDate")),
                "imagen": imagen,
                "seccion": _texto(item.find("category")),
            }
        )
    return notas


def parsear_fecha(valor):
    """Fechas RFC 822 (RSS) o ISO (sitemaps). Devuelve (fecha, estimada)."""
    fecha = None
    if valor:
        try:
            fecha = parsedate_to_datetime(valor)
        except (TypeError, ValueError, IndexError):
            fecha = parse_date(valor)
    if fecha is None or timezone.is_naive(fecha):
        return timezone.now(), True
    return fecha, False


def _contenido_arc(soup):
    """Sitios hechos con Arc (Página/12) guardan la nota en Fusion.globalContent."""
    for script in soup.find_all("script"):
        codigo = script.string or ""
        inicio = codigo.find("Fusion.globalContent=")
        if inicio < 0:
            continue
        try:
            datos, _ = json.JSONDecoder().raw_decode(codigo, inicio + len("Fusion.globalContent="))
        except ValueError:
            return "", ""
        parrafos = [
            _limpiar_html(e.get("content", ""))
            for e in datos.get("content_elements", [])
            if isinstance(e, dict) and e.get("type") == "text"
        ]
        seccion = ((datos.get("taxonomy") or {}).get("primary_section") or {}).get("name", "")
        return "\n\n".join(p for p in parrafos if p), seccion
    return "", ""


def extraer_texto(soup, spec):
    """Texto completo y sección de la página de una nota.

    Devuelve ("", seccion) si la nota es exclusiva para suscriptores: no se
    reproduce contenido pago.
    """
    datos = article_metadata(soup)
    seccion = datos.get("articleSection") or ""
    if isinstance(seccion, list):
        seccion = seccion[0] if seccion else ""
    if str(datos.get("isAccessibleForFree", "true")).lower() in ("false", "0"):
        return "", seccion
    cuerpo = datos.get("articleBody") or ""
    if isinstance(cuerpo, str) and cuerpo.strip():
        texto = BeautifulSoup(cuerpo, "html.parser").get_text("\n", strip=True)
    else:
        texto, seccion_arc = _contenido_arc(soup)
        seccion = seccion or seccion_arc
    # Selectores de respaldo, en orden, hasta encontrar texto suficiente.
    selectores = spec.get("parrafos") or ()
    for selector in (selectores,) if isinstance(selectores, str) else selectores:
        if len(texto) >= TEXTO_MINIMO:
            break
        parrafos = [p.get_text(" ", strip=True) for p in soup.select(selector)]
        # Los textos muy cortos son botones o créditos ("Compartí esta nota").
        texto = "\n\n".join(dict.fromkeys(p for p in parrafos if len(p) >= PARRAFO_MINIMO))
    return texto, seccion


def fetch_feed(session, url, deadline):
    return fetch_bytes(session, url, url, deadline, accept=("xml", "rss"))


def run_feed(nombre, force=False):
    spec = FEEDS[nombre]
    origen = spec["urls"][0]
    with source_lock(spec["medio"]):
        key = "scrape-result:" + nombre
        previous = cache.get(key)
        if previous and not force:
            return {**previous, "cached": True}
        run = ScrapeRun.objects.create(fuente=nombre)
        errors = []
        try:
            deadline = time.monotonic() + settings.SCRAPE_BUDGET_SECONDS
            with requests.Session() as session:
                session.headers.update(
                    {"User-Agent": "DesenchufadasNews/1.0 (+https://www.desenchufadas.com)"}
                )
                items = []
                for url in spec["urls"]:
                    try:
                        items.extend(leer_feed(fetch_feed(session, url, deadline)))
                    except (requests.RequestException, ScrapeError, ET.ParseError) as exc:
                        errors.append(type(exc).__name__)
                        logger.warning("Canal omitido fuente=%s causa=%s", nombre, type(exc).__name__)
                if not items:
                    raise ScrapeError("No se pudo leer ningún canal del medio.")
                medio, _ = Medio.objects.get_or_create(nombre=spec["medio"])
                limite = timezone.now() + timedelta(days=1)
                vistos = set()
                for item in items:
                    # Al agotar el tiempo se sigue en la próxima pasada: no es una falla.
                    if run.detectadas >= settings.FEED_MAX_ITEMS or time.monotonic() >= deadline:
                        break
                    try:
                        url = allowed_url(item["url"], origen)
                        if (
                            url in vistos
                            or not item["titulo"]
                            or urlsplit(url).path.startswith(spec.get("excluir", ()))
                        ):
                            continue
                        vistos.add(url)
                        run.detectadas += 1
                        if Noticia.objects.filter(medio=medio, url=url).exists():
                            run.existentes += 1
                            continue
                        fecha, estimada = parsear_fecha(item["fecha"])
                        if fecha > limite:
                            raise ScrapeError("Fecha de publicación futura no válida.")
                        texto, seccion, portada = "", item["seccion"], item["imagen"]
                        try:
                            # Algunos medios reenvían a sus subdominios (exitoina.perfil.com).
                            pagina = fetch_html(session, url, origen, deadline, subdomains=True)
                            texto, seccion_pagina = extraer_texto(pagina, spec)
                            seccion = seccion_pagina or seccion
                            og = pagina.select_one('meta[property="og:image"]')
                            portada = portada or (og.get("content", "") if og else "")
                        except (requests.RequestException, ScrapeError) as exc:
                            logger.info("Sin texto fuente=%s causa=%s", nombre, type(exc).__name__)
                        completa = len(texto) >= TEXTO_MINIMO
                        categoria = categoria_por_url(url)
                        if categoria == "GENERAL":
                            categoria = categoria_por_seccion(seccion)
                        if categoria == "GENERAL":
                            categoria = categoria_por_seccion(urlsplit(url).path.replace("/", " "))
                        persist_article(
                            {
                                "titulo": item["titulo"][:500],
                                "descripcion": item["descripcion"][:1000],
                                "contenido": texto if completa else "",
                                "fecha": fecha,
                                "fecha_estimada": estimada,
                                "portada": image_url(portada, url),
                                "categoria_nombre": categoria,
                                "imagenes": [],
                                "url": url,
                                "solo_tendencias": not completa,
                            },
                            medio,
                        )
                        run.guardadas += 1
                    except (ScrapeError, ValueError) as exc:
                        # Una nota suelta inválida (otro dominio, fecha rara) no es una falla del medio.
                        run.omitidas += 1
                        logger.info("Nota omitida fuente=%s causa=%s", nombre, exc)
            if not run.guardadas and not run.existentes:
                errors.append("SinNotasValidas")
            run.estado = "partial" if errors else "success"
            result = {
                "source": nombre,
                "saved": run.guardadas,
                "known": run.existentes,
                "skipped": run.omitidas,
                "status": run.estado,
                "run_id": run.pk,
            }
            cache.set(key, result, 300)
            return result
        except Exception as exc:
            run.estado = "failed"
            run.error = str(exc)[:1000] if isinstance(exc, ScrapeError) else type(exc).__name__
            logger.error("Actualización fallida fuente=%s causa=%s", nombre, type(exc).__name__)
            raise ScrapeError("No se pudo actualizar la fuente.") from exc
        finally:
            run.fin = timezone.now()
            if errors and not run.error:
                run.error = ", ".join(sorted(set(errors)))[:1000]
            run.save()
