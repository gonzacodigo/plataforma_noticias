from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from applications.cuentas.models import Visita
from applications.medio.models import Medio
from applications.tendencias.models import Tendencia
from .models import Categoria, CopyGenerado, GeneracionIA, Noticia
from .services import entregas, ia
from .tests import usuario_cliente

GENERAR = "applications.noticia.services.ia.generar"


def resultado(texto="Texto de prueba"):
    return {"texto": texto, "modelo": "claude-haiku-5-5", "tokens_entrada": 90, "tokens_salida": 40}


@override_settings(COPY_IA_HABILITADO=True, COPY_IA_LIMITE_MENSUAL=10)
class HerramientasNoticiaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.categoria = Categoria.objects.create(nombre="ESPECTACULOS")
        cls.noticia = Noticia.objects.create(
            titulo="Lali anunció un show",
            descripcion="Será en marzo",
            contenido="La cantante confirmó la fecha.",
            fecha=timezone.now(),
            medio=Medio.objects.create(nombre="INFOBAE"),
            categoria=cls.categoria,
            url="https://www.infobae.com/teleshow/lali/",
        )
        cls.ana = usuario_cliente("ana")
        cls.beto = usuario_cliente("beto")

    def url(self, tipo):
        return f"/detail-noticia/{self.noticia.pk}/ia/{tipo}/"

    def test_cada_formato_usa_sus_instrucciones(self):
        self.client.force_login(self.ana)
        for tipo in ("resumen", "copy", "guion"):
            with patch(GENERAR, return_value=resultado(tipo)) as generar:
                response = self.client.post(self.url(tipo))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["texto"], tipo)
            self.assertEqual(generar.call_args.args[0], tipo)
            self.assertIn("Lali anunció un show", generar.call_args.args[1])
        self.assertEqual(
            sorted(CopyGenerado.objects.values_list("tipo", flat=True)), ["copy", "guion", "resumen"]
        )

    def test_formato_desconocido_es_404(self):
        self.client.force_login(self.ana)
        with patch(GENERAR) as generar:
            self.assertEqual(self.client.post(self.url("poema")).status_code, 404)
        generar.assert_not_called()

    def test_otro_cliente_recibe_la_misma_generacion_sin_llamar_a_la_api(self):
        self.client.force_login(self.ana)
        with patch(GENERAR, return_value=resultado("Copy de Ana")):
            self.client.post(self.url("copy"))
        self.client.force_login(self.beto)
        with patch(GENERAR) as generar:
            response = self.client.post(self.url("copy"))
        generar.assert_not_called()
        self.assertEqual(response.json()["texto"], "Copy de Ana")
        entrega = CopyGenerado.objects.get(usuario=self.beto)
        self.assertTrue(entrega.reutilizada)
        self.assertEqual((entrega.tokens_entrada, entrega.tokens_salida), (0, 0))
        self.assertEqual(GeneracionIA.objects.count(), 1)
        # Cuenta para el límite igual que una generación nueva.
        self.assertEqual(response.json()["restantes"], 9)

    def test_otra_version_siempre_llama_a_la_api(self):
        self.client.force_login(self.ana)
        with patch(GENERAR, return_value=resultado("Primera")):
            self.client.post(self.url("copy"))
        self.client.force_login(self.beto)
        with patch(GENERAR, return_value=resultado("Segunda")) as generar:
            response = self.client.post(self.url("copy"), {"nueva": "1"})
        generar.assert_called_once()
        self.assertEqual(response.json()["texto"], "Segunda")
        self.assertFalse(CopyGenerado.objects.get(usuario=self.beto).reutilizada)

    def test_no_se_repite_una_generacion_al_mismo_usuario(self):
        self.client.force_login(self.ana)
        with patch(GENERAR, return_value=resultado("Primera")):
            self.client.post(self.url("copy"))
        with patch(GENERAR, return_value=resultado("Segunda")) as generar:
            self.client.post(self.url("copy"))
        generar.assert_called_once()

    def test_reutiliza_solo_mismo_formato_y_contenido(self):
        self.client.force_login(self.ana)
        with patch(GENERAR, return_value=resultado("Resumen")):
            self.client.post(self.url("resumen"))
        Noticia.objects.filter(pk=self.noticia.pk).update(contenido="Cambió la nota.")
        self.client.force_login(self.beto)
        with patch(GENERAR, return_value=resultado("Copy")) as generar:
            self.client.post(self.url("copy"))
            self.client.post(self.url("resumen"))
        self.assertEqual(generar.call_count, 2)

    def test_editar_y_ver_la_version_propia(self):
        self.client.force_login(self.ana)
        with patch(GENERAR, return_value=resultado("Original")):
            data = self.client.post(self.url("guion")).json()
        response = self.client.post(data["guardar_url"], {"texto": "Mi versión editada"})
        self.assertEqual(response.json(), {"ok": True})
        entrega = CopyGenerado.objects.get(usuario=self.ana)
        self.assertEqual(entrega.texto, "Mi versión editada")
        self.assertIsNotNone(entrega.editado)
        # El original queda intacto para los demás clientes.
        self.assertEqual(entrega.generacion.texto, "Original")
        pagina = self.client.get(self.noticia.get_absolute_url())
        self.assertContains(pagina, "Mi versión editada")
        self.assertContains(pagina, "Generar otra versión")
        self.client.force_login(self.beto)
        with patch(GENERAR) as generar:
            self.assertEqual(self.client.post(self.url("guion")).json()["texto"], "Original")
        generar.assert_not_called()

    def test_no_se_edita_lo_ajeno_ni_vacio(self):
        self.client.force_login(self.ana)
        with patch(GENERAR, return_value=resultado()):
            data = self.client.post(self.url("copy")).json()
        self.assertEqual(self.client.post(data["guardar_url"], {"texto": "  "}).status_code, 400)
        self.client.force_login(self.beto)
        self.assertEqual(self.client.post(data["guardar_url"], {"texto": "hack"}).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.post(data["guardar_url"], {"texto": "x"}).status_code, 403)

    def test_limite_compartido_entre_formatos(self):
        self.client.force_login(usuario_cliente("caro", limite_copys_mensual=2))
        with patch(GENERAR, return_value=resultado()):
            estados = [
                self.client.post(self.url(tipo)).status_code for tipo in ("resumen", "copy", "guion")
            ]
        self.assertEqual(estados, [200, 200, 429])

    def test_falla_de_la_api_no_cuenta(self):
        self.client.force_login(self.ana)
        with patch(GENERAR, side_effect=ia.CopyIAError("x")):
            self.assertEqual(self.client.post(self.url("resumen")).status_code, 502)
        self.assertFalse(CopyGenerado.objects.exists())
        self.assertFalse(GeneracionIA.objects.exists())

    def test_registra_la_visita_con_el_formato(self):
        self.client.force_login(self.ana)
        with patch(GENERAR, return_value=resultado()):
            self.client.post(self.url("guion"))
        visita = Visita.objects.get(seccion="copy_ia")
        self.assertEqual(visita.noticia_id, self.noticia.pk)
        self.assertEqual(visita.filtros.get("formato"), "guion")


@override_settings(COPY_IA_HABILITADO=True, COPY_IA_LIMITE_MENSUAL=10)
class ResumenTendenciaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        categoria = Categoria.objects.create(nombre="ESPECTACULOS")
        ahora = timezone.now()
        cls.notas = [
            Noticia.objects.create(
                titulo=f"Nota de {medio}",
                contenido=f"Lo que contó {medio}.",
                fecha=ahora,
                medio=Medio.objects.create(nombre=medio),
                categoria=categoria,
                url=f"https://{medio.lower()}.com/nota/",
            )
            for medio in ("INFOBAE", "TN", "CLARIN", "TELEFE")
        ]
        cls.tendencia = Tendencia.objects.create(
            categoria=categoria,
            titulo="La historia del día",
            primera_aparicion=ahora,
            ultima_aparicion=ahora,
            cantidad_medios=3,
            cantidad_notas=3,
        )
        cls.tendencia.noticias.set(cls.notas[:3])
        cls.ana = usuario_cliente("ana")
        cls.beto = usuario_cliente("beto")
        cls.url = f"/tendencia/{cls.tendencia.pk}/ia/resumen/"

    def test_exige_cuenta(self):
        with patch(GENERAR) as generar:
            self.assertIn(self.client.post(self.url).status_code, (302, 403))
        generar.assert_not_called()

    def test_genera_con_todas_las_fuentes_y_reutiliza(self):
        self.client.force_login(self.ana)
        with patch(GENERAR, return_value=resultado("Resumen de varias fuentes")) as generar:
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        tipo, contenido = generar.call_args.args
        self.assertEqual(tipo, "resumen_tendencia")
        for medio in ("INFOBAE", "TN", "CLARIN"):
            self.assertIn(f"· {medio}", contenido)
        self.assertNotIn("TELEFE", contenido)
        entrega = CopyGenerado.objects.get()
        self.assertEqual((entrega.tendencia, entrega.noticia), (self.tendencia, None))
        visita = Visita.objects.get(seccion="copy_ia")
        self.assertIsNone(visita.noticia_id)
        self.assertEqual(visita.filtros.get("tendencia"), self.tendencia.pk)

        self.client.force_login(self.beto)
        with patch(GENERAR) as generar:
            self.assertEqual(self.client.post(self.url).json()["texto"], "Resumen de varias fuentes")
        generar.assert_not_called()

    def test_avisa_cuando_la_tendencia_suma_notas(self):
        self.client.force_login(self.ana)
        with patch(GENERAR, return_value=resultado("Resumen viejo")):
            self.client.post(self.url)
        pagina = self.client.get(self.tendencia.get_absolute_url())
        self.assertContains(pagina, "Resumen viejo")
        self.assertNotContains(pagina, "Se sumaron notas nuevas")
        self.tendencia.noticias.add(self.notas[3])
        pagina = self.client.get(self.tendencia.get_absolute_url())
        self.assertContains(pagina, "Se sumaron notas nuevas")
        self.assertContains(pagina, 'name="nueva" value="0"')
        # La versión nueva no reutiliza la vieja: la huella cambió.
        self.client.force_login(self.beto)
        with patch(GENERAR, return_value=resultado("Resumen nuevo")) as generar:
            self.client.post(self.url)
        generar.assert_called_once()
        self.assertIn("TELEFE", generar.call_args.args[1])

    def test_pagina_muestra_la_herramienta(self):
        self.client.force_login(self.ana)
        pagina = self.client.get(self.tendencia.get_absolute_url())
        self.assertContains(pagina, "Resumen de la tendencia")
        self.assertContains(pagina, self.url)

    def test_huella_ignora_el_orden(self):
        h1 = entregas.huella_actual("resumen_tendencia", tendencia=self.tendencia)
        self.tendencia.noticias.set(list(reversed(self.notas[:3])))
        self.assertEqual(h1, entregas.huella_actual("resumen_tendencia", tendencia=self.tendencia))


class ModeloTests(TestCase):
    @override_settings(COPY_IA_MODELO="claude-haiku-5-5", IA_MODELOS={"guion": "claude-sonnet-5-5"})
    def test_modelo_por_formato(self):
        self.assertEqual(ia.modelo_para("copy"), "claude-haiku-5-5")
        self.assertEqual(ia.modelo_para("guion"), "claude-sonnet-5-5")
        self.assertFalse(ia._admite_respaldo("claude-haiku-5-5"))
        self.assertTrue(ia._admite_respaldo("claude-sonnet-5-5"))
