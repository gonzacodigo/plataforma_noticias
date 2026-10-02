"""Bounded, transactional news ingestion shared by all source adapters."""

import json
import logging
import os
import re
import socket
import ipaddress
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from applications.noticia.models import Noticia, Categoria, NoticiaImagen, ScrapeRun
from applications.medio.models import Medio

logger = logging.getLogger(__name__)
SOURCES = {
    "infobae": (
        "INFOBAE",
        "https://www.infobae.com/",
        "a.story-card-ctn",
        ".story-card-hl",
        "article.article, .body-article",
        "p.paragraph",
        ".article-subheadline",
        ".sharebar-article-date",
    ),
    "infobae_show": (
        "INFOBAE",
        "https://www.infobae.com/teleshow/",
        "a.story-card-ctn",
        ".story-card-hl",
        ".body-article, article.article",
        "p.paragraph",
        ".article-subheadline",
        ".sharebar-article-date",
    ),
    "tn": (
        "TN",
        "https://tn.com.ar/",
        ".card__body, article.card__container",
        ".card__headline",
        ".col-content",
        ".paragraph",
        ".article__dropline",
        ".time__value",
    ),
    "tn_show": (
        "TN",
        "https://tn.com.ar/show/",
        "article.card__container, .card__body",
        ".card__headline",
        ".col-content",
        ".paragraph",
        ".article__dropline",
        ".time__value",
    ),
    "telefe": (
        "TELEFE",
        "https://noticias.mitelefe.com/",
        "article.card, a:has(h1), a.e-card-link",
        "h1, h2, h3, .e-card-title",
        "article.col-lg-8, article.b-post",
        ".e-post-text, .article-body p",
        ".e-post-subtitle",
        ".e-post-time",
    ),
    "telefe_show": (
        "TELEFE",
        "https://noticias.mitelefe.com/espectaculos/",
        "article.card, a:has(h1), a.e-card-link",
        "h1, h2, h3, .e-card-title",
        "article.col-lg-8, article.b-post",
        ".e-post-text, .article-body p",
        ".e-post-subtitle",
        ".e-post-time",
    ),
    "clarin": (
        "CLARIN",
        "https://www.clarin.com/",
        "article",
        "h2.title, h2",
        "article",
        ".container-text, .text-embed",
        ".storySummary",
        "time",
    ),
}


class ScrapeError(Exception):
    pass


class ScrapeBusy(ScrapeError):
    pass


def canonical_url(url):
    parts = urlsplit(url)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise ScrapeError("URL de origen no válida.")
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            urlencode(sorted(query)),
            "",
        )
    )


def allowed_url(url, origin, check_dns=False):
    url = canonical_url(url)
    parts = urlsplit(url)
    domain = urlsplit(origin).hostname.removeprefix("www.")
    if parts.hostname.removeprefix("www.") != domain or parts.port not in (
        None,
        80,
        443,
    ):
        raise ScrapeError("Enlace fuera del medio permitido.")
    if check_dns:
        try:
            addresses = socket.getaddrinfo(
                parts.hostname,
                parts.port or (443 if parts.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
            if not addresses or any(
                not ipaddress.ip_address(item[4][0]).is_global for item in addresses
            ):
                raise ScrapeError("La fuente debe resolver a direcciones públicas.")
        except OSError as exc:
            raise ScrapeError("No se pudo resolver la fuente.") from exc
    return url


def fetch_html(session, url, origin, deadline):
    for _ in range(4):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ScrapeError("Tiempo máximo de actualización alcanzado.")
        url = allowed_url(url, origin, check_dns=True)
        with session.get(
            url,
            timeout=(min(5, remaining), min(12, remaining)),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            response.raise_for_status()
            if "html" not in response.headers.get("Content-Type", "text/html").lower():
                raise ScrapeError("La fuente no devolvió HTML.")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 8 * 1024 * 1024 or time.monotonic() > deadline:
                    raise ScrapeError("Respuesta demasiado grande o lenta.")
                chunks.append(chunk)
            return BeautifulSoup(b"".join(chunks), "html.parser")
    raise ScrapeError("Demasiadas redirecciones.")


@contextmanager
def source_lock(name):
    folder = Path(settings.BASE_DIR) / ".cache" / "locks"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / (name + ".lock")).open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ScrapeBusy("Actualización en curso.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


MONTHS = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}


def parse_date(value):
    if not value or not isinstance(value, str):
        return None
    value = " ".join(value.split())
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (
            timezone.make_aware(parsed, ZoneInfo(settings.TIME_ZONE))
            if timezone.is_naive(parsed)
            else parsed
        )
    except ValueError:
        pass
    match = re.search(
        r"(\d{1,2})\s+(?:de\s+)?([a-záéíóú]+)\s+(?:de\s+)?(\d{4})(?:.*?(\d{1,2}):(\d{2}))?",
        value.lower(),
    )
    if not match or match[2][:3] not in MONTHS:
        return None
    try:
        hour, minute = int(match[4] or 0), int(match[5] or 0)
        if "p.m." in value.lower() or " pm" in value.lower():
            hour = hour % 12 + 12
        elif "a.m." in value.lower() or " am" in value.lower():
            hour %= 12
        return datetime(
            int(match[3]),
            MONTHS[match[2][:3]],
            int(match[1]),
            hour,
            minute,
            tzinfo=ZoneInfo(settings.TIME_ZONE),
        )
    except ValueError:
        return None


def article_metadata(soup):
    def walk(value):
        if isinstance(value, list):
            for item in value:
                yield from walk(item)
        elif isinstance(value, dict):
            kinds = value.get("@type", [])
            if isinstance(kinds, str):
                kinds = [kinds]
            if set(kinds) & {
                "NewsArticle",
                "Article",
                "ReportageNewsArticle",
                "BlogPosting",
            }:
                yield value
            if "@graph" in value:
                yield from walk(value["@graph"])

    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            for item in walk(json.loads(tag.string or tag.get_text())):
                return item
        except (ValueError, TypeError):
            continue
    return {}


def image_url(value, origin):
    if not isinstance(value, str) or not value.strip():
        return ""
    value = urljoin(origin, value)
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or len(value) > 2000
        ):
            return ""
        if parts.hostname in ("localhost", None):
            return ""
        try:
            if not ipaddress.ip_address(parts.hostname).is_global:
                return ""
        except ValueError:
            pass
        return value
    except ValueError:
        return ""


def extract_article(soup, title, url, source):
    spec = SOURCES[source]
    metadata = article_metadata(soup)
    root = soup.select_one(spec[4]) or soup.select_one("article")
    body = metadata.get("articleBody", "")
    if isinstance(body, str) and body.strip():
        body = BeautifulSoup(body, "html.parser").get_text("\n", strip=True)
    elif root:
        paragraphs = root.select(spec[5]) or root.select("p")
        body = "\n\n".join(
            dict.fromkeys(
                p.get_text(" ", strip=True)
                for p in paragraphs
                if p.get_text(strip=True)
            )
        )
    else:
        body = ""
    if source.startswith("telefe") and root:
        paragraphs = root.select("p")
        extracted = "\n\n".join(
            dict.fromkeys(
                p.get_text(" ", strip=True)
                for p in paragraphs
                if p.get_text(strip=True)
            )
        )
        if len(extracted) > len(body):
            body = extracted
    if not body.strip():
        raise ScrapeError("Artículo sin contenido legible.")
    desc_tag = soup.select_one(spec[6]) or soup.select_one(
        'meta[property="og:description"]'
    )
    description = metadata.get("description") or (
        (desc_tag.get("content") or desc_tag.get_text(" ", strip=True))
        if desc_tag
        else ""
    )
    date_tag = soup.select_one(
        'meta[property="article:published_time"], time[datetime]'
    ) or soup.select_one(spec[7])
    date_value = metadata.get("datePublished") or (
        (
            date_tag.get("content")
            or date_tag.get("datetime")
            or date_tag.get_text(" ", strip=True)
        )
        if date_tag
        else ""
    )
    published = parse_date(date_value)
    estimated = published is None
    published = published or timezone.now()
    if published > timezone.now() + timedelta(days=1):
        raise ScrapeError("Fecha de publicación futura no válida.")
    image = metadata.get("image", "")
    if isinstance(image, list):
        image = image[0] if image else ""
    if isinstance(image, dict):
        image = image.get("url", "")
    og = soup.select_one('meta[property="og:image"]')
    cover = image_url(image or (og.get("content") if og else ""), url)
    images = list(
        dict.fromkeys(
            image_url(tag.get("src") or tag.get("data-src"), url)
            for tag in (root.select("img") if root else [])
        )
    )
    segments = urlsplit(url).path.lower().split("/")
    categories = {
        "teleshow": "ESPECTACULOS",
        "show": "ESPECTACULOS",
        "espectaculos": "ESPECTACULOS",
        "deportes": "DEPORTES",
        "politica": "POLITICA",
        "economia": "ECONOMIA",
        "policiales": "POLICIALES",
        "internacional": "INTERNACIONAL",
        "mundo": "INTERNACIONAL",
    }
    category = next((categories[x] for x in segments if x in categories), "GENERAL")
    if source.endswith("_show"):
        category = "ESPECTACULOS"
    return {
        "titulo": title[:500],
        "descripcion": str(description)[:1000],
        "contenido": body,
        "fecha": published,
        "fecha_estimada": estimated,
        "portada": cover,
        "categoria_nombre": category,
        "imagenes": [u for u in images if u and u != cover][:30],
        "url": url,
    }


@transaction.atomic
def persist_article(data, medium):
    data = data.copy()
    images = data.pop("imagenes")
    category, _ = Categoria.objects.get_or_create(nombre=data.pop("categoria_nombre"))
    old = Noticia.objects.filter(medio=medium, url=data["url"]).first()
    if old and data["fecha_estimada"]:
        data["fecha"] = old.fecha
        data["fecha_estimada"] = old.fecha_estimada
    article, _ = Noticia.objects.update_or_create(
        medio=medium, url=data.pop("url"), defaults={**data, "categoria": category}
    )
    for image in images:
        NoticiaImagen.objects.get_or_create(noticia=article, url=image)
    return article


def run_source(source, force=False):
    if source not in SOURCES:
        raise ScrapeError("Fuente desconocida.")
    spec = SOURCES[source]
    with source_lock(spec[0]):
        key = "scrape-result:" + source
        previous = cache.get(key)
        if previous and not force:
            return {**previous, "cached": True}
        run = ScrapeRun.objects.create(fuente=source)
        errors = []
        try:
            deadline = time.monotonic() + settings.SCRAPE_BUDGET_SECONDS
            with requests.Session() as session:
                session.headers.update(
                    {
                        "User-Agent": "DesenchufadasNews/1.0 (+https://www.desenchufadas.com)"
                    }
                )
                soup = fetch_html(session, spec[1], spec[1], deadline)
                cards = soup.select(spec[2])
                if not cards:
                    raise ScrapeError(
                        "La estructura de la portada no coincide con el adaptador."
                    )
                medium, _ = Medio.objects.get_or_create(nombre=spec[0])
                seen = set()
                for card in cards:
                    if (
                        run.detectadas >= settings.SCRAPE_MAX_ARTICLES
                        or time.monotonic() >= deadline
                    ):
                        break
                    title = card.select_one(spec[3])
                    link = card if card.name == "a" else card.select_one("a[href]")
                    if not title or not title.get_text(strip=True) or not link:
                        continue
                    try:
                        url = allowed_url(
                            urljoin(spec[1], link.get("href", "")), spec[1]
                        )
                        if (
                            url in seen
                            or "/watch" in urlsplit(url).path
                            or (
                                source.startswith("telefe")
                                and not re.search(r"pid\d+", urlsplit(url).path)
                            )
                        ):
                            continue
                        seen.add(url)
                        run.detectadas += 1
                        article = fetch_html(session, url, spec[1], deadline)
                        data = extract_article(
                            article, title.get_text(" ", strip=True), url, source
                        )
                        persist_article(data, medium)
                        run.guardadas += 1
                    except (requests.RequestException, ScrapeError, ValueError) as exc:
                        run.omitidas += 1
                        errors.append(type(exc).__name__)
                        logger.warning(
                            "Artículo omitido fuente=%s causa=%s",
                            source,
                            type(exc).__name__,
                        )
                if not run.guardadas:
                    raise ScrapeError("No se pudo extraer ningún artículo válido.")
            run.estado = (
                "partial" if errors or time.monotonic() >= deadline else "success"
            )
            result = {
                "source": source,
                "saved": run.guardadas,
                "skipped": run.omitidas,
                "status": run.estado,
                "run_id": run.pk,
            }
            cache.set(key, result, 300)
            return result
        except Exception as exc:
            run.estado = "failed"
            run.error = (
                str(exc)[:1000] if isinstance(exc, ScrapeError) else type(exc).__name__
            )
            logger.error(
                "Actualización fallida fuente=%s causa=%s", source, type(exc).__name__
            )
            raise ScrapeError("No se pudo actualizar la fuente.") from exc
        finally:
            run.fin = timezone.now()
            if errors and not run.error:
                run.error = ", ".join(errors)[:1000]
            run.save()
            logger.info(
                "Actualización fuente=%s estado=%s detectadas=%s guardadas=%s omitidas=%s",
                source,
                run.estado,
                run.detectadas,
                run.guardadas,
                run.omitidas,
            )
