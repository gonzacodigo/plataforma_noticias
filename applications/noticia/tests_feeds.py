from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from applications.cuentas.models import Cliente, Perfil
from applications.medio.models import Medio
from applications.tendencias.models import Tendencia
from applications.tendencias.servicio import calcular_tendencias
from .models import Categoria, Noticia, ScrapeRun
from .services.engine import ScrapeError, allowed_url
from .services.feeds import (
    FEEDS,
    categoria_por_seccion,
    extraer_texto,
    leer_feed,
    parsear_fecha,
    run_feed,
)

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>
<title>Perfil</title>
<item>
  <title><![CDATA[Guido Kaczka se quebr\xc3\xb3 al anunciar la muerte de su mam\xc3\xa1]]></title>
  <link>https://perfil.com/noticias/espectaculos/guido-kaczka-mama.phtml</link>
  <pubDate>Mon, 23 Nov 2026 21:32:49 GMT</pubDate>
  <media:content url="https://media.perfil.com/foto.jpg" medium="image" />
  <description><![CDATA[<p><img src="https://media.perfil.com/foto.jpg" /></p>El conductor se despidi\xc3\xb3 al aire.<ul><li><a href="/otra">Nota relacionada</a></li></ul>]]></description>
  <category><![CDATA[Espect\xc3\xa1culos]]></category>
</item>
<item>
  <title>Fuerte rebote en Wall Street</title>
  <link>https://www.ambito.com/finanzas/rebote-n123</link>
  <pubDate>Mon, 23 Nov 2026 17:49:00 -0300</pubDate>
  <enclosure length="0" type="image/jpeg" url="https://media.ambito.com/a.jpg"/>
  <description>Los ADRs suben.</description>
</item>
</channel></rss>"""

SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
 xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"
 xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
<url><loc>https://www.pagina12.com.ar/2026/11/23/no-tenemos-esas-nostalgias/</loc>
<news:news><news:publication_date>2026-11-23T21:56:56.284Z</news:publication_date>
<news:title><![CDATA[No tenemos esas nostalgias]]></news:title></news:news>
<image:image><image:loc>https://pagina12.arc-cdn.net/foto.webp</image:loc></image:image></url>
</urlset>"""

PARRAFO = "Este es un párrafo de la nota con suficiente texto para contar como contenido real. "


def pagina(cuerpo="", ld=None):
    ld_json = f'<script type="application/ld+json">{ld}</script>' if ld else ""
    return BeautifulSoup(f"<html><head>{ld_json}</head><body>{cuerpo}</body></html>", "html.parser")


class LecturaTests(SimpleTestCase):
    def test_rss(self):
        notas = leer_feed(RSS)
        self.assertEqual(len(notas), 2)
        perfil, ambito = notas
        self.assertEqual(perfil["titulo"], "Guido Kaczka se quebró al anunciar la muerte de su mamá")
        self.assertEqual(perfil["imagen"], "https://media.perfil.com/foto.jpg")
        self.assertEqual(perfil["descripcion"], "El conductor se despidió al aire.")  # sin relacionadas
        self.assertEqual(perfil["seccion"], "Espectáculos")
        self.assertEqual(ambito["imagen"], "https://media.ambito.com/a.jpg")

    def test_sitemap_de_noticias(self):
        (nota,) = leer_feed(SITEMAP)
        self.assertEqual(nota["titulo"], "No tenemos esas nostalgias")
        self.assertEqual(nota["url"], "https://www.pagina12.com.ar/2026/11/23/no-tenemos-esas-nostalgias/")
        self.assertEqual(nota["imagen"], "https://pagina12.arc-cdn.net/foto.webp")
        fecha, estimada = parsear_fecha(nota["fecha"])
        self.assertFalse(estimada)
        self.assertEqual((fecha.year, fecha.month, fecha.day), (2026, 11, 23))

    def test_fechas(self):
        self.assertFalse(parsear_fecha("Mon, 23 Nov 2026 17:49:00 -0300")[1])
        self.assertTrue(parsear_fecha("")[1])
        self.assertTrue(parsear_fecha("cualquier cosa")[1])

    def test_categoria_por_seccion(self):
        casos = {
            "Espectáculos": "ESPECTACULOS", "Entretenimiento": "ESPECTACULOS", "El país": "POLITICA",
            "Finanzas": "ECONOMIA", "El mundo": "INTERNACIONAL", "Fútbol": "DEPORTES",
            "Sociedad": "GENERAL", "": "GENERAL",
        }
        for seccion, esperada in casos.items():
            with self.subTest(seccion=seccion):
                self.assertEqual(categoria_por_seccion(seccion), esperada)

    def test_texto_desde_json_ld(self):
        ld = '{"@type": "NewsArticle", "articleBody": "%s", "articleSection": "Sociedad"}' % (PARRAFO * 4)
        texto, seccion = extraer_texto(pagina(ld=ld), FEEDS["c5n"])
        self.assertIn("párrafo de la nota", texto)
        self.assertEqual(seccion, "Sociedad")

    def test_no_copia_notas_pagas(self):
        ld = '{"@type": "NewsArticle", "isAccessibleForFree": false, "articleBody": "%s"}' % (PARRAFO * 4)
        self.assertEqual(extraer_texto(pagina(f"<article><p>{PARRAFO}</p></article>", ld), FEEDS["perfil"])[0], "")

    def test_texto_de_arc_pagina12(self):
        script = (
            '<script>window.x=1;Fusion.globalContent={"content_elements":['
            f'{{"type":"text","content":"<p>{PARRAFO}</p>"}},{{"type":"image","url":"x"}},'
            f'{{"type":"text","content":"<p>{PARRAFO}Segundo.</p>"}}],'
            '"taxonomy":{"primary_section":{"name":"El país"}}};Fusion.otro={};</script>'
        )
        texto, seccion = extraer_texto(pagina(script), FEEDS["pagina12"])
        self.assertEqual(texto.count("párrafo de la nota"), 2)
        self.assertEqual(seccion, "El país")

    def test_selectores_de_respaldo_y_sin_botones(self):
        cuerpo = f"<article><p>Compartí esta nota</p><p>{PARRAFO}</p><p>{PARRAFO}Más.</p><p>{PARRAFO}Fin.</p></article>"
        texto, _ = extraer_texto(pagina(cuerpo), FEEDS["perfil"])
        self.assertNotIn("Compartí", texto)
        self.assertIn("Fin.", texto)

    def test_subdominios_solo_si_se_permiten(self):
        url = "https://exitoina.perfil.com/noticias/nota"
        with self.assertRaises(ScrapeError):
            allowed_url(url, "https://www.perfil.com/feed")
        self.assertEqual(allowed_url(url, "https://www.perfil.com/feed", subdomains=True), url)
        with self.assertRaises(ScrapeError):
            allowed_url("https://perfil.com.evil.com/x", "https://www.perfil.com/feed", subdomains=True)


class IngestaTests(TestCase):
    def setUp(self):
        cache.clear()

    def ejecutar(self, nombre, feed, paginas):
        def html(session, url, origen, deadline, subdomains=False):
            if url not in paginas:
                raise ScrapeError("sin página")
            return pagina(paginas[url])

        with patch("applications.noticia.services.feeds.fetch_feed", return_value=feed), \
                patch("applications.noticia.services.feeds.fetch_html", side_effect=html):
            return run_feed(nombre, force=True)

    def test_guarda_completas_y_resumen_cuando_no_hay_texto(self):
        paginas = {
            "https://perfil.com/noticias/espectaculos/guido-kaczka-mama.phtml":
                f"<div class='news-body'><p>{PARRAFO}Uno.</p><p>{PARRAFO}Dos.</p><p>{PARRAFO}Fin.</p></div>",
        }
        r = self.ejecutar("perfil", RSS, paginas)
        self.assertEqual((r["status"], r["saved"], r["skipped"]), ("success", 1, 1))  # Ámbito: otro dominio
        nota = Noticia.objects.get()
        self.assertEqual((nota.medio.nombre, nota.categoria.nombre), ("PERFIL", "ESPECTACULOS"))
        self.assertFalse(nota.solo_tendencias)
        self.assertIn("Fin.", nota.contenido)
        self.assertEqual(nota.portada, "https://media.perfil.com/foto.jpg")

        Noticia.objects.all().delete()
        cache.clear()
        r = self.ejecutar("perfil", RSS, {})  # la página no responde: queda como resumen
        nota = Noticia.objects.get()
        self.assertTrue(nota.solo_tendencias)
        self.assertEqual(nota.contenido, "")

    def test_no_duplica_y_respeta_exclusiones(self):
        feed = RSS.replace(b"https://perfil.com/noticias/espectaculos/", b"https://www.lanacion.com.ar/espectaculos/").replace(
            b"https://www.ambito.com/finanzas/", b"https://www.lanacion.com.ar/politica/")
        self.ejecutar("lanacion", feed, {})
        self.assertEqual(list(Noticia.objects.values_list("url", flat=True)),
                         ["https://www.lanacion.com.ar/politica/rebote-n123"])
        cache.clear()
        r = self.ejecutar("lanacion", feed, {})
        self.assertEqual((r["saved"], r["known"]), (0, 1))

    def test_canal_caido_falla_y_se_registra(self):
        with patch("applications.noticia.services.feeds.fetch_feed", side_effect=ScrapeError("caído")):
            with self.assertRaises(ScrapeError):
                run_feed("c5n", force=True)
        self.assertEqual(ScrapeRun.objects.get().estado, "failed")

    def test_comando_acepta_fuentes_rss(self):
        with patch("applications.noticia.management.commands.actualizar_noticias.run_source",
                   return_value={"saved": 3, "known": 0, "skipped": 0, "status": "success"}) as run:
            call_command("actualizar_noticias", fuente="pagina12", stdout=StringIO())
        run.assert_called_once_with("pagina12", force=False)


class SitioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Categoria.objects.create(nombre="POLITICA")
        cls.perfil = Medio.objects.create(nombre="PERFIL")
        cls.completa = Noticia.objects.create(titulo="Nota completa de Perfil", contenido="Texto",
                                              fecha=timezone.now(), medio=cls.perfil, categoria=cat,
                                              url="https://perfil.com/a")
        cls.resumen = Noticia.objects.create(titulo="Nota paga de Perfil", fecha=timezone.now(),
                                             medio=cls.perfil, categoria=cat, url="https://perfil.com/b",
                                             solo_tendencias=True)

    def test_listado_muestra_completas_y_oculta_resumenes(self):
        r = self.client.get("/")
        self.assertContains(r, "Nota completa de Perfil")
        self.assertNotContains(r, "Nota paga de Perfil")
        self.assertNotContains(self.client.get("/", {"kword": "Perfil"}), "Nota paga")
        self.assertContains(r, '>PERFIL</option>')  # el medio aparece en el filtro

    def test_tarjeta_de_resumen_lleva_al_medio_original(self):
        from django.template.loader import render_to_string

        html = render_to_string("noticia/_card.html", {"noticia": self.resumen})
        self.assertIn('href="https://perfil.com/b"', html)
        self.assertIn("Leer en PERFIL", html)
        self.assertIn('target="_blank"', html)
        html = render_to_string("noticia/_card.html", {"noticia": self.completa})
        self.assertIn(f'href="{self.completa.get_absolute_url()}"', html)


@override_settings(TENDENCIAS_MIN_MEDIOS=3, TENDENCIAS_MIN_MEDIOS_GENERAL=4)
class UmbralGeneralTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.show = Categoria.objects.create(nombre="ESPECTACULOS")
        cls.politica = Categoria.objects.create(nombre="POLITICA")
        cls.medios = [Medio.objects.create(nombre=n) for n in ("TN", "INFOBAE", "CLARIN", "PERFIL")]

    def historia(self, categoria, medios, titulo):
        for i in range(medios):
            Noticia.objects.create(
                titulo=f"{titulo} versión {i}", fecha=timezone.now() - timedelta(minutes=i),
                medio=self.medios[i], categoria=categoria, url=f"https://x.com/{categoria.pk}/{medios}/{i}",
            )

    def test_general_exige_cuatro_medios_y_espectaculos_tres(self):
        self.historia(self.politica, 3, "El Senado aprobó la ley de ludopatía con cambios")
        self.historia(self.show, 3, "Wanda Nara y Marta Fort hablaron de la separación")
        calcular_tendencias()
        self.assertEqual(list(Tendencia.objects.values_list("categoria__nombre", flat=True)), ["ESPECTACULOS"])
        Noticia.objects.create(titulo="El Senado aprobó la ley de ludopatía tras un largo debate",
                               fecha=timezone.now(), medio=self.medios[3], categoria=self.politica,
                               url="https://x.com/extra")
        calcular_tendencias()
        self.assertEqual(Tendencia.objects.filter(categoria=self.politica, activa=True).count(), 1)
