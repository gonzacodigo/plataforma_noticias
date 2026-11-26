from django.test import TestCase, override_settings


class ArchivosDelSitioTests(TestCase):
    def test_robots_txt_es_publico_y_bloquea_lo_privado(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        texto = response.content.decode()
        for ruta in ("/admin/", "/detail-noticia/", "/tendencia/", "/ingresar/"):
            self.assertIn(f"Disallow: {ruta}", texto)

    def test_favicon_redirige_al_svg(self):
        response = self.client.get("/favicon.ico")
        self.assertEqual(response.status_code, 301)
        self.assertIn("brand-mark", response["Location"])

    @override_settings(DEBUG=False)
    def test_404_propia_en_castellano(self):
        response = self.client.get("/no-existe-esta-pagina/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "desenchufó", status_code=404)
        self.assertContains(response, "noindex", status_code=404)
