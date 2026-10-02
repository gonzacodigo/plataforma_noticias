import json
import tempfile
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from bs4 import BeautifulSoup
from django.test import TestCase, SimpleTestCase, override_settings, Client
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction, connection
from django.utils import timezone
from django.test.utils import CaptureQueriesContext
from applications.medio.models import Medio
from .models import Noticia, Categoria, NoticiaImagen, ScrapeRun
from .services.engine import (
    parse_date,
    canonical_url,
    allowed_url,
    extract_article,
    persist_article,
    run_source,
    SOURCES,
    ScrapeError,
    ScrapeBusy,
    source_lock,
    fetch_html,
)


class SiteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.medium = Medio.objects.create(nombre="TN")
        cls.category = Categoria.objects.create(nombre="POLITICA")
        cls.news = Noticia.objects.create(
            titulo="Una noticia especial",
            descripcion="Descripción",
            contenido="<img src=x onerror=alert(1)><br><br>Otro párrafo",
            fecha=timezone.now(),
            medio=cls.medium,
            categoria=cls.category,
            url="https://tn.com.ar/politica/especial/",
        )

    def test_invalid_filters_are_validation_errors(self):
        for params in [
            {"fecha1": "invalid"},
            {"medio": "abc"},
            {"categoria": "abc"},
            {"categorias": ["abc"]},
            {"fecha1": "2026-10-10", "fecha2": "2026-10-01"},
        ]:
            with self.subTest(params=params):
                response = self.client.get("/", params)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertEqual(response.context["paginator"].count, 0)

    def test_combined_filters(self):
        response = self.client.get(
            "/", {"kword": "NO_MATCH", "fecha1": "2020-01-01", "fecha2": "2030-01-01"}
        )
        self.assertEqual(response.context["paginator"].count, 0)
        response = self.client.get(
            "/",
            {
                "kword": "especial",
                "medio": self.medium.pk,
                "categoria": self.category.pk,
            },
        )
        self.assertEqual(response.context["paginator"].count, 1)

    def test_open_date_range(self):
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.assertEqual(
            self.client.get("/", {"fecha1": tomorrow}).context["paginator"].count, 0
        )
        self.assertEqual(
            self.client.get("/", {"fecha2": tomorrow}).context["paginator"].count, 1
        )

    def test_pagination_and_preserved_filters(self):
        Noticia.objects.bulk_create(
            [
                Noticia(
                    titulo=f"especial {i}",
                    fecha=timezone.now(),
                    categoria=self.category,
                    medio=self.medium,
                )
                for i in range(30)
            ]
        )
        response = self.client.get("/", {"kword": "especial"})
        self.assertEqual(len(response.context["noticias"]), 24)
        self.assertContains(response, "kword=especial&amp;page=2")
        self.assertEqual(
            len(
                self.client.get("/", {"kword": "especial", "page": 2}).context[
                    "noticias"
                ]
            ),
            7,
        )

    def test_query_count_is_bounded(self):
        Noticia.objects.bulk_create(
            [
                Noticia(
                    titulo=str(i),
                    fecha=timezone.now(),
                    categoria=self.category,
                    medio=self.medium,
                )
                for i in range(40)
            ]
        )
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 5)

    def test_xss_is_escaped_and_legacy_breaks_preserved(self):
        response = self.client.get(self.news.get_absolute_url())
        self.assertNotContains(response, "<img src=x onerror=alert(1)>")
        self.assertContains(response, "&lt;img src=x onerror=alert(1)&gt;")
        self.assertContains(response, "Otro párrafo")

    def test_detail_visit_once_per_session(self):
        for _ in range(2):
            self.client.get(self.news.get_absolute_url())
        self.news.refresh_from_db()
        self.assertEqual(self.news.visitas, 1)

    def test_public_pages_do_not_trigger_ingestion(self):
        with patch("applications.noticia.views.run_source") as scrape:
            for url in [
                "/",
                "/instagram-views",
                "/buscador-imagenes",
                "/noticia-medio/",
                "/noticia-categoria/",
                self.news.get_absolute_url(),
            ]:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "fetch(")
            scrape.assert_not_called()

    def test_valid_document_and_security_headers(self):
        response = self.client.get("/")
        soup = BeautifulSoup(response.content, "html.parser")
        self.assertEqual(len(soup.find_all("html")), 1)
        self.assertEqual(len(soup.find_all("head")), 1)
        self.assertEqual(soup.html["lang"], "es-AR")
        self.assertIn("script-src 'self'", response["Content-Security-Policy"])
        self.assertNotContains(response, "jquery")

    def test_sharing_title_and_canonical(self):
        response = self.client.get(self.news.get_absolute_url())
        self.assertContains(response, "Una+noticia+especial")
        self.assertContains(response, "https://www.desenchufadas.com/detail-noticia/")

    def test_anonymous_cannot_scrape(self):
        with patch("applications.noticia.views.run_source") as scrape:
            self.assertEqual(self.client.post("/api/noticias/tn/").status_code, 403)
            scrape.assert_not_called()

    def test_staff_post_only(self):
        user = get_user_model().objects.create_user(
            "staff", password="pass", is_staff=True
        )
        self.client.force_login(user)
        with patch(
            "applications.noticia.views.run_source", return_value={"saved": 1}
        ) as scrape:
            self.assertEqual(self.client.get("/api/noticias/tn/").status_code, 405)
            self.assertEqual(self.client.post("/api/noticias/tn/").status_code, 200)
            scrape.assert_called_once_with("tn")

    def test_staff_requires_csrf(self):
        user = get_user_model().objects.create_user(
            "secure", password="pass", is_staff=True
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        self.assertEqual(client.post("/api/noticias/tn/").status_code, 403)

    def test_not_staff_denied(self):
        user = get_user_model().objects.create_user("reader", password="pass")
        self.client.force_login(user)
        self.assertEqual(self.client.post("/api/noticias/tn/").status_code, 403)

    def test_duplicate_url_blocked(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Noticia.objects.create(
                titulo="other",
                fecha=timezone.now(),
                medio=self.medium,
                categoria=self.category,
                url=self.news.url,
            )

    def test_category_and_medium_protected(self):
        from django.db.models.deletion import ProtectedError

        with self.assertRaises(ProtectedError):
            self.medium.delete()
        with self.assertRaises(ProtectedError):
            self.category.delete()


class ExtractionTests(SimpleTestCase):
    def test_spanish_dates(self):
        for date in [
            "28 Sep 2026 01:10 p.m.",
            "28 de septiembre de 2026, 13:10 hs",
            "28 septiembre 2026 13:10",
        ]:
            parsed = parse_date(date)
            self.assertEqual((parsed.month, parsed.hour), (9, 13))
        self.assertEqual(parse_date("2026-09-28T13:10:00Z").hour, 13)

    def test_invalid_dates(self):
        for value in [None, "", "incompleta", "32 enero 2026", "5 desconocido 2026"]:
            self.assertIsNone(parse_date(value))

    def test_canonicalization(self):
        self.assertEqual(
            canonical_url("https://tn.com.ar/a?utm_source=x&b=2#frag"),
            "https://tn.com.ar/a?b=2",
        )

    def test_source_url_restrictions(self):
        for url in [
            "https://evil.example/a",
            "https://tn.com.ar:8080/a",
            "file:///tmp/a",
            "https://user:pass@tn.com.ar/a",
        ]:
            with self.assertRaises(ScrapeError):
                allowed_url(url, "https://tn.com.ar/")

    def test_structured_data_for_every_source(self):
        metadata = {
            "@type": "NewsArticle",
            "articleBody": "Primer párrafo. Segundo párrafo.",
            "datePublished": "2026-09-01T12:00:00-03:00",
            "description": "Descripción real",
        }
        soup = BeautifulSoup(
            '<script type="application/ld+json">'
            + json.dumps({"@graph": [metadata]})
            + "</script>",
            "html.parser",
        )
        for source in SOURCES:
            with self.subTest(source=source):
                data = extract_article(
                    soup, "title", SOURCES[source][1] + "teleshow/a/", source
                )
                self.assertEqual(data["descripcion"], "Descripción real")
                self.assertFalse(data["fecha_estimada"])
                self.assertTrue(data["contenido"])
                self.assertEqual(data["categoria_nombre"], "ESPECTACULOS")

    def test_empty_content_rejected(self):
        for source in SOURCES:
            with self.subTest(source=source), self.assertRaises(ScrapeError):
                extract_article(
                    BeautifulSoup("<article></article>", "html.parser"),
                    "title",
                    SOURCES[source][1],
                    source,
                )

    def test_future_date_rejected(self):
        soup = BeautifulSoup(
            '<article><p>Body</p></article><time datetime="2099-01-01"></time>',
            "html.parser",
        )
        with self.assertRaises(ScrapeError):
            extract_article(
                soup, "title", "https://www.clarin.com/politica/a", "clarin"
            )

    def test_html_entities_stay_text(self):
        soup = BeautifulSoup(
            '<article class="article"><p class="paragraph">&lt;img src=x onerror=alert(1)&gt;</p></article>',
            "html.parser",
        )
        data = extract_article(
            soup, "title", "https://www.infobae.com/teleshow/a/", "infobae"
        )
        self.assertEqual(data["contenido"], "<img src=x onerror=alert(1)>")
        self.assertTrue(data["fecha_estimada"])

    def test_process_lock_rejects_parallel_work(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(
            BASE_DIR=Path(folder)
        ):
            with source_lock("TN"):
                with self.assertRaises(ScrapeBusy), source_lock("TN"):
                    pass
            with source_lock("TN"):
                pass


class PersistenceTests(TestCase):
    def setUp(self):
        self.medium = Medio.objects.create(nombre="TN")
        self.data = {
            "titulo": "A",
            "descripcion": "d",
            "contenido": "text",
            "fecha": timezone.now(),
            "fecha_estimada": False,
            "portada": "",
            "categoria_nombre": "GENERAL",
            "imagenes": ["https://example.com/a.jpg"],
            "url": "https://tn.com.ar/a/",
        }

    def test_idempotent_update(self):
        first = persist_article(self.data, self.medium)
        updated = persist_article(
            {**self.data, "titulo": "Título corregido"}, self.medium
        )
        self.assertEqual(first.pk, updated.pk)
        self.assertEqual(Noticia.objects.count(), 1)
        self.assertEqual(NoticiaImagen.objects.count(), 1)
        self.assertEqual(updated.titulo, "Título corregido")

    def test_images_and_article_are_atomic(self):
        with patch(
            "applications.noticia.services.engine.NoticiaImagen.objects.get_or_create",
            side_effect=RuntimeError("fixture"),
        ):
            with self.assertRaises(RuntimeError):
                persist_article(self.data, self.medium)
        self.assertEqual(Noticia.objects.count(), 0)
        self.assertEqual(Categoria.objects.count(), 0)

    def test_same_title_different_media_is_kept(self):
        persist_article(self.data, self.medium)
        persist_article(self.data, Medio.objects.create(nombre="OTHER"))
        self.assertEqual(Noticia.objects.count(), 2)

    def test_estimated_update_preserves_original_date(self):
        first = persist_article(self.data, self.medium)
        second = persist_article(
            {
                **self.data,
                "fecha_estimada": True,
                "fecha": timezone.now() + timedelta(hours=1),
            },
            self.medium,
        )
        self.assertEqual(first.fecha, second.fecha)
        self.assertFalse(second.fecha_estimada)

    def test_run_cache_and_record(self):
        from django.core.cache import cache

        cache.clear()
        listing = BeautifulSoup(
            '<div class="card__body"><a href="/politica/a"><h2 class="card__headline">A</h2></a></div>',
            "html.parser",
        )
        article = BeautifulSoup(
            '<div class="col-content"><p class="paragraph">Content</p></div>',
            "html.parser",
        )
        with tempfile.TemporaryDirectory() as folder, override_settings(
            BASE_DIR=Path(folder)
        ):
            with patch(
                "applications.noticia.services.engine.fetch_html",
                side_effect=[listing, article],
            ) as fetch:
                result = run_source("tn")
                self.assertEqual(result["saved"], 1)
                self.assertTrue(run_source("tn")["cached"])
                self.assertEqual(fetch.call_count, 2)
        self.assertEqual(ScrapeRun.objects.get().estado, "success")

    def test_changed_selector_is_failure(self):
        from django.core.cache import cache

        cache.clear()
        with tempfile.TemporaryDirectory() as folder, override_settings(
            BASE_DIR=Path(folder)
        ):
            with patch(
                "applications.noticia.services.engine.fetch_html",
                return_value=BeautifulSoup("<html></html>", "html.parser"),
            ):
                with self.assertRaises(ScrapeError):
                    run_source("clarin")
        self.assertEqual(ScrapeRun.objects.get().estado, "failed")


class NetworkBoundaryTests(SimpleTestCase):
    def response(self, status=200, headers=None, chunks=None):
        from unittest.mock import MagicMock

        response = MagicMock()
        response.status_code = status
        response.headers = headers or {"Content-Type": "text/html"}
        response.iter_content.return_value = chunks or [
            b"<html><h1>fixture</h1></html>"
        ]
        response.__enter__.return_value = response
        return response

    def test_public_dns_required(self):
        with patch(
            "applications.noticia.services.engine.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("127.0.0.1", 443))],
        ):
            with self.assertRaises(ScrapeError):
                allowed_url("https://tn.com.ar/a", "https://tn.com.ar/", check_dns=True)

    def test_fetch_uses_timeouts_and_streaming(self):
        from unittest.mock import MagicMock
        import time

        session = MagicMock()
        session.get.return_value = self.response()
        with patch(
            "applications.noticia.services.engine.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 443))],
        ):
            soup = fetch_html(
                session,
                "https://tn.com.ar/a",
                "https://tn.com.ar/",
                time.monotonic() + 20,
            )
        self.assertEqual(soup.h1.get_text(), "fixture")
        self.assertEqual(session.get.call_args.kwargs["allow_redirects"], False)
        self.assertTrue(session.get.call_args.kwargs["stream"])
        self.assertEqual(len(session.get.call_args.kwargs["timeout"]), 2)

    def test_redirect_to_other_domain_blocked(self):
        from unittest.mock import MagicMock
        import time

        session = MagicMock()
        session.get.return_value = self.response(
            302, {"Location": "https://evil.example/a"}
        )
        with patch(
            "applications.noticia.services.engine.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 443))],
        ):
            with self.assertRaises(ScrapeError):
                fetch_html(
                    session,
                    "https://tn.com.ar/a",
                    "https://tn.com.ar/",
                    time.monotonic() + 20,
                )
        self.assertEqual(session.get.call_count, 1)

    def test_response_size_bounded(self):
        from unittest.mock import MagicMock
        import time

        session = MagicMock()
        session.get.return_value = self.response(chunks=[b"x" * (9 * 1024 * 1024)])
        with patch(
            "applications.noticia.services.engine.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 443))],
        ):
            with self.assertRaises(ScrapeError):
                fetch_html(
                    session,
                    "https://tn.com.ar/a",
                    "https://tn.com.ar/",
                    time.monotonic() + 20,
                )

    def test_deadline_blocks_request(self):
        from unittest.mock import MagicMock
        import time

        session = MagicMock()
        with self.assertRaises(ScrapeError):
            fetch_html(
                session,
                "https://tn.com.ar/a",
                "https://tn.com.ar/",
                time.monotonic() - 1,
            )
        session.get.assert_not_called()


class OperationalTests(TestCase):
    def test_health(self):
        self.assertEqual(self.client.get("/salud/").json(), {"status": "ok"})
        with patch(
            "noticias.urls.connection.cursor",
            side_effect=RuntimeError("private diagnostic"),
        ):
            response = self.client.get("/salud/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})

    def test_partial_command_alerts(self):
        from io import StringIO
        from django.core.management import call_command, CommandError

        with patch(
            "applications.noticia.management.commands.actualizar_noticias.run_source",
            return_value={"saved": 2, "skipped": 1, "status": "partial"},
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "actualizar_noticias",
                    fuente="tn",
                    stdout=StringIO(),
                    stderr=StringIO(),
                )

    def test_unsafe_legacy_source_url_hidden(self):
        category = Categoria.objects.create(nombre="GENERAL")
        medium = Medio.objects.create(nombre="TEST")
        news = Noticia.objects.create(
            titulo="Test",
            fecha=timezone.now(),
            categoria=category,
            medio=medium,
            url="javascript:alert(1)",
        )
        self.assertEqual(news.source_url, "")
        self.assertNotContains(
            self.client.get(news.get_absolute_url()), "javascript:alert(1)"
        )
