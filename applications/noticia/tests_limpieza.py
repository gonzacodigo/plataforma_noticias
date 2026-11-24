from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from applications.cuentas.models import Visita
from applications.medio.models import Medio
from applications.tendencias.models import Tendencia
from .models import Categoria, CopyGenerado, Noticia, NoticiaAlias, NoticiaImagen
from .services.limpieza import MARCA_PENDIENTE, podar_noticias


@override_settings(NOTICIAS_MAXIMO=10, NOTICIAS_CONSERVAR=5)
class PodaNoticiasTests(TestCase):
    def setUp(self):
        cache.clear()
        self.medio = Medio.objects.create(nombre="TN")
        self.categoria = Categoria.objects.create(nombre="ESPECTACULOS")
        self.ahora = timezone.now()

    def crear(self, cantidad):
        # La nota i se publicó hace i días: la 0 es la más nueva.
        return [
            Noticia.objects.create(
                titulo=f"nota {i}",
                fecha=self.ahora - timedelta(days=i),
                medio=self.medio,
                categoria=self.categoria,
                url=f"https://tn.com.ar/{i}/",
            )
            for i in range(cantidad)
        ]

    def test_debajo_del_maximo_no_borra(self):
        self.crear(9)
        r = podar_noticias()
        self.assertEqual(r["borradas"], 0)
        self.assertEqual(Noticia.objects.count(), 9)

    def test_al_llegar_al_maximo_deja_las_mas_nuevas(self):
        notas = self.crear(12)
        r = podar_noticias()
        self.assertEqual(r["borradas"], 7)
        self.assertEqual(
            set(Noticia.objects.values_list("titulo", flat=True)),
            {f"nota {i}" for i in range(5)},
        )
        self.assertEqual(r["hasta"], notas[5].fecha)

    def test_borra_imagenes_y_alias_y_conserva_visitas_y_copys(self):
        notas = self.crear(12)
        vieja = notas[-1]
        NoticiaImagen.objects.create(noticia=vieja, url="https://tn.com.ar/a.jpg")
        NoticiaImagen.objects.create(noticia=notas[0], url="https://tn.com.ar/b.jpg")
        NoticiaAlias.objects.create(original_id=999999, noticia=vieja)
        usuario = get_user_model().objects.create_user("ana")
        copy = CopyGenerado.objects.create(usuario=usuario, noticia=vieja, texto="copy", modelo="m")
        visita = Visita.objects.create(usuario=usuario, seccion="detalle", ruta="/x/", noticia=vieja)

        podar_noticias()

        self.assertEqual(list(NoticiaImagen.objects.values_list("url", flat=True)), ["https://tn.com.ar/b.jpg"])
        self.assertFalse(NoticiaAlias.objects.exists())
        copy.refresh_from_db()
        visita.refresh_from_db()
        self.assertIsNone(copy.noticia)
        self.assertIsNone(visita.noticia)
        self.assertEqual(copy.texto, "copy")

    def test_no_borra_notas_de_tendencias_activas(self):
        notas = self.crear(12)
        activa = Tendencia.objects.create(
            categoria=self.categoria, titulo="activa", nota_principal=notas[-1],
            primera_aparicion=self.ahora, ultima_aparicion=self.ahora,
        )
        activa.noticias.add(notas[-1])
        vieja = Tendencia.objects.create(
            categoria=self.categoria, titulo="vieja", activa=False, nota_principal=notas[-2],
            primera_aparicion=self.ahora, ultima_aparicion=self.ahora,
        )
        vieja.noticias.add(notas[-2])

        podar_noticias()

        self.assertTrue(Noticia.objects.filter(pk=notas[-1].pk).exists())
        self.assertFalse(Noticia.objects.filter(pk=notas[-2].pk).exists())
        vieja.refresh_from_db()
        self.assertIsNone(vieja.nota_principal)
        self.assertEqual(vieja.noticias.count(), 0)

    def test_borra_en_tandas(self):
        self.crear(12)
        r = podar_noticias(lote=2)
        self.assertEqual(r["borradas"], 7)
        self.assertEqual(Noticia.objects.count(), 5)

    def test_sin_tiempo_sigue_en_la_proxima_corrida(self):
        self.crear(12)
        # Sin tiempo: borra una sola tanda y deja la marca de pendiente.
        r = podar_noticias(lote=2, segundos=0)
        self.assertEqual((r["borradas"], r["completa"]), (2, False))
        self.assertTrue(cache.get(MARCA_PENDIENTE))
        r = podar_noticias(lote=2, segundos=0)
        self.assertEqual(Noticia.objects.count(), 8)
        # Quedan 8, debajo del máximo (10): sigue igual porque estaba pendiente.
        r = podar_noticias(lote=2)
        self.assertTrue(r["completa"])
        self.assertEqual(Noticia.objects.count(), 5)
        self.assertIsNone(cache.get(MARCA_PENDIENTE))
        # Ya en el mínimo y sin marca: no borra más.
        self.assertEqual(podar_noticias()["borradas"], 0)

    def test_simular_no_borra(self):
        self.crear(12)
        out = StringIO()
        call_command("podar_noticias", simular=True, stdout=out)
        self.assertIn("borraría 7 noticias", out.getvalue())
        self.assertEqual(Noticia.objects.count(), 12)

    def test_comando_con_limites_propios(self):
        self.crear(12)
        out = StringIO()
        call_command("podar_noticias", maximo=12, conservar=10, stdout=out)
        self.assertIn("borró 2 noticias", out.getvalue())
        self.assertEqual(Noticia.objects.count(), 10)

    def test_limites_invalidos(self):
        with self.assertRaises(ValueError):
            podar_noticias(maximo=5, conservar=5)

    def test_actualizar_noticias_poda_al_final(self):
        self.crear(12)
        out = StringIO()
        with patch(
            "applications.noticia.management.commands.actualizar_noticias.run_source",
            return_value={"saved": 0, "known": 0, "skipped": 0, "status": "success"},
        ):
            call_command("actualizar_noticias", paralelo=1, stdout=out)
        self.assertIn("poda: 7 noticias viejas borradas", out.getvalue())
        self.assertEqual(Noticia.objects.count(), 5)

    def test_falla_de_la_poda_no_frena_la_ingesta(self):
        err = StringIO()
        with patch(
            "applications.noticia.management.commands.actualizar_noticias.run_source",
            return_value={"saved": 0, "known": 0, "skipped": 0, "status": "success"},
        ), patch(
            "applications.noticia.services.limpieza.podar_noticias", side_effect=RuntimeError("x")
        ), self.assertLogs("applications.noticia.management.commands.actualizar_noticias", "ERROR"):
            call_command("actualizar_noticias", paralelo=1, stdout=StringIO(), stderr=err)
        self.assertIn("poda: no se pudo completar", err.getvalue())
