from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from applications.cuentas.models import Cliente, Perfil, Visita
from applications.medio.models import Medio
from applications.noticia.models import Categoria, Noticia
from .models import Tendencia
from .motor import agrupar, puntaje
from .servicio import calcular_tendencias, top_por_categoria

AHORA = timezone.now()


def nota(i, titulo, medio, minutos=0, descripcion=""):
    return SimpleNamespace(
        id=i, titulo=titulo, descripcion=descripcion, medio_id=medio,
        fecha_ingesta=AHORA - timedelta(minutes=minutos),
    )


class MotorTests(SimpleTestCase):
    def test_agrupa_la_misma_historia_contada_distinto(self):
        notas = [
            nota(1, "Wanda Nara fulminó al ex de Marta Fort y reveló el consejo que le dio tras la separación", 1, 90),
            nota(2, "Wanda Nara contó los consejos que le dio a Marta Fort para que supere su separación", 2, 80),
            nota(3, "Los consejos de Wanda Nara a Marta Fort por su separación: “No me cayó bien”", 3, 70),
            nota(4, "Catherine Fulop volvió a Venezuela después de 14 años y se reencontró con su mamá", 1, 60),
            nota(5, "La emoción de Catherine Fulop por su regreso a Venezuela después de 14 años", 2, 50),
            nota(6, "Boca venció 2-0 a Atlético Mineiro y es campeón de la Copa Sudamericana", 3, 40),
        ]
        grupos = sorted((sorted(n.id for n in g) for g in agrupar(notas)), key=len, reverse=True)
        self.assertEqual(grupos[:2], [[1, 2, 3], [4, 5]])
        self.assertIn([6], grupos)

    def test_no_mezcla_historias_que_solo_comparten_un_nombre(self):
        notas = [
            nota(1, "Wanda Nara reveló los consejos que le dio a Marta Fort tras la separación", 1, 30),
            nota(2, "Marcela Tauro detectó moretones en la cara de Wanda Nara", 2, 20),
        ]
        self.assertEqual(len(agrupar(notas)), 2)

    def test_puntaje(self):
        self.assertGreater(puntaje(5, 5, 0), puntaje(3, 10, 0))  # más medios gana a más notas
        self.assertGreater(puntaje(4, 4, 1), puntaje(4, 4, 20))  # lo reciente gana
        self.assertAlmostEqual(puntaje(3, 3, 12), puntaje(3, 3, 0) / 2)  # vida media de 12 h
        self.assertGreater(puntaje(3, 3, 0, lecturas=10), puntaje(3, 3, 0))


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.show = Categoria.objects.create(nombre="ESPECTACULOS")
        cls.politica = Categoria.objects.create(nombre="POLITICA")
        cls.medios = [Medio.objects.create(nombre=n) for n in ("TN", "INFOBAE", "PRONTO", "CLARIN")]

    def crear(self, titulo, medio, minutos, categoria=None, publicado_antes=0):
        return Noticia.objects.create(
            titulo=titulo, fecha=timezone.now() - timedelta(minutes=minutos + publicado_antes),
            medio=self.medios[medio],
            categoria=categoria or self.show, url=f"https://x.com/{titulo[:20]}-{medio}-{minutos}",
            fecha_ingesta=timezone.now() - timedelta(minutes=minutos),
        )

    def historia_wanda(self):
        return [
            self.crear("Wanda Nara fulminó al ex de Marta Fort y reveló el consejo tras la separación", 2, 120),
            self.crear("Wanda Nara contó los consejos que le dio a Marta Fort tras su separación", 0, 90),
            self.crear("Los consejos de Wanda Nara a Marta Fort por su separación", 1, 60),
        ]


class ServicioTests(Base):
    def test_crea_tendencia_con_tres_medios_y_titulo_de_la_primera_nota(self):
        notas = self.historia_wanda()
        r = calcular_tendencias()
        self.assertEqual((r["activas"], r["nuevas"]), (1, 1))
        t = Tendencia.objects.get()
        self.assertEqual(t.titulo, notas[0].titulo)
        self.assertEqual(t.nota_principal, notas[0])
        self.assertEqual((t.cantidad_medios, t.cantidad_notas, t.categoria), (3, 3, self.show))
        self.assertEqual(t.medios, ["INFOBAE", "PRONTO", "TN"])
        self.assertEqual(set(t.noticias.all()), set(notas))

    def test_el_titulo_es_de_la_nota_publicada_primero_aunque_se_descargue_despues(self):
        notas = self.historia_wanda()
        tardia = self.crear(
            "Wanda Nara y los consejos que le dio a Marta Fort por la separación", 3, 10, publicado_antes=300
        )
        calcular_tendencias()
        t = Tendencia.objects.get()
        self.assertEqual((t.titulo, t.nota_principal), (tardia.titulo, tardia))
        self.assertEqual(t.primera_aparicion, tardia.fecha)
        self.assertEqual(t.ultima_aparicion, notas[2].fecha)

    def test_dos_medios_no_alcanzan(self):
        self.crear("Wanda Nara contó los consejos que le dio a Marta Fort tras su separación", 0, 30)
        self.crear("Los consejos de Wanda Nara a Marta Fort por su separación", 1, 20)
        calcular_tendencias()
        self.assertFalse(Tendencia.objects.exists())

    def test_mismo_medio_repetido_no_cuenta_doble(self):
        for i in range(3):
            self.crear(f"Wanda Nara contó los consejos a Marta Fort tras su separación {i}", 0, 30 + i)
        calcular_tendencias()
        self.assertFalse(Tendencia.objects.exists())

    def test_conserva_la_tendencia_entre_calculos_y_la_actualiza(self):
        self.historia_wanda()
        calcular_tendencias()
        pk = Tendencia.objects.get().pk
        self.crear("Wanda Nara habló de los consejos a Marta Fort por la separación", 3, 5)
        r = calcular_tendencias()
        t = Tendencia.objects.get()
        self.assertEqual((t.pk, t.cantidad_medios, t.cantidad_notas, r["nuevas"]), (pk, 4, 4, 0))

    @override_settings(TENDENCIAS_VENTANA_HORAS=1)
    def test_se_desactiva_al_salir_de_la_ventana(self):
        self.historia_wanda()
        Tendencia.objects.create(
            categoria=self.show, titulo="vieja", primera_aparicion=timezone.now(), ultima_aparicion=timezone.now()
        )
        calcular_tendencias()
        self.assertFalse(Tendencia.objects.get(titulo="vieja").activa)

    def test_categoria_es_la_mayoritaria(self):
        self.crear("Wanda Nara fulminó al ex de Marta Fort y reveló el consejo tras la separación", 2, 120, self.politica)
        self.crear("Wanda Nara contó los consejos que le dio a Marta Fort tras su separación", 0, 90)
        self.crear("Los consejos de Wanda Nara a Marta Fort por su separación", 1, 60)
        calcular_tendencias()
        self.assertEqual(Tendencia.objects.get().categoria, self.show)

    def test_suma_lecturas_de_clientes(self):
        notas = self.historia_wanda()
        user = get_user_model().objects.create_user("lector")
        for _ in range(4):
            Visita.objects.create(usuario=user, seccion="detalle", ruta="/", noticia=notas[1])
        calcular_tendencias()
        self.assertEqual(Tendencia.objects.get().lecturas, 4)

    def test_oculta_se_mantiene_y_no_se_muestra(self):
        self.historia_wanda()
        calcular_tendencias()
        Tendencia.objects.update(oculta=True)
        calcular_tendencias()
        self.assertTrue(Tendencia.objects.get().oculta)
        self.assertEqual(top_por_categoria(), [])

    def test_dos_apartados_espectaculos_y_general_con_top_tres(self):
        ahora = timezone.now()
        deportes = Categoria.objects.create(nombre="DEPORTES")
        general = Categoria.objects.create(nombre="GENERAL")

        def crear(categoria, titulo, puntos):
            Tendencia.objects.create(categoria=categoria, titulo=titulo, puntaje=puntos,
                                     primera_aparicion=ahora, ultima_aparicion=ahora)

        for i in range(5):
            crear(self.show, f"show {i}", 10 + i)
        crear(self.politica, "política", 99)
        crear(deportes, "deportes", 50)
        crear(general, "general", 30)
        crear(deportes, "deportes flojo", 1)
        top = top_por_categoria()
        self.assertEqual([etiqueta for etiqueta, _ in top], ["Espectáculos", "General"])
        self.assertEqual([t.titulo for t in top[0][1]], ["show 4", "show 3", "show 2"])
        self.assertEqual([t.titulo for t in top[1][1]], ["política", "deportes", "general"])

    def test_sin_tendencias_de_otras_categorias_solo_espectaculos(self):
        ahora = timezone.now()
        Tendencia.objects.create(categoria=self.show, titulo="show", puntaje=5,
                                 primera_aparicion=ahora, ultima_aparicion=ahora)
        self.assertEqual([etiqueta for etiqueta, _ in top_por_categoria()], ["Espectáculos"])


class VistasTests(Base):
    def setUp(self):
        self.historia_wanda()
        calcular_tendencias()
        self.tendencia = Tendencia.objects.get()
        user = get_user_model().objects.create_user("cliente", password="x")
        Perfil.objects.create(usuario=user, cliente=Cliente.objects.create(nombre="C"))
        self.cliente = user

    def test_portada_publica_muestra_el_bloque_como_gancho(self):
        r = self.client.get("/")
        self.assertContains(r, "En tendencia")
        self.assertContains(r, self.tendencia.titulo)
        self.assertContains(r, "3 medios")
        self.assertContains(r, self.tendencia.get_absolute_url())
        self.assertContains(r, "Ingresá con tu cuenta")

    def test_no_aparece_con_filtros_ni_en_otras_listas(self):
        for url in ["/?kword=Wanda", "/?page=1", "/noticia-categoria/", "/noticia-medio/"]:
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), 'id="tendencias"')

    def test_detalle_requiere_cuenta(self):
        url = self.tendencia.get_absolute_url()
        self.assertRedirects(self.client.get(url), f"/ingresar/?next={url}", fetch_redirect_response=False)

    def test_detalle_para_clientes_en_orden_y_registrado(self):
        self.client.force_login(self.cliente)
        r = self.client.get(self.tendencia.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual([n.medio.nombre for n in r.context["noticias"]], ["PRONTO", "TN", "INFOBAE"])
        self.assertContains(r, "CÓMO LA CONTÓ CADA MEDIO")
        visita = Visita.objects.get(seccion="tendencia")
        self.assertEqual(visita.filtros, {"tendencia": self.tendencia.pk})

    def test_oculta_da_404(self):
        Tendencia.objects.update(oculta=True)
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(self.tendencia.get_absolute_url()).status_code, 404)

    def test_admin(self):
        self.client.force_login(get_user_model().objects.create_superuser("admin", password="x"))
        for url in ["/admin/tendencias/tendencia/", f"/admin/tendencias/tendencia/{self.tendencia.pk}/change/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class ComandosTests(Base):
    def test_calcular_tendencias(self):
        self.historia_wanda()
        out = StringIO()
        call_command("calcular_tendencias", stdout=out)
        self.assertIn("1 activas", out.getvalue())

    def test_actualizar_noticias_recalcula_y_una_falla_no_frena_la_ingesta(self):
        resultado = {"saved": 0, "skipped": 0, "status": "success"}
        with patch("applications.noticia.management.commands.actualizar_noticias.run_source", return_value=resultado):
            with patch("applications.tendencias.servicio.calcular_tendencias", return_value={"activas": 2, "nuevas": 1}) as calc:
                out = StringIO()
                call_command("actualizar_noticias", fuente="tn", stdout=out, stderr=StringIO())
            calc.assert_called_once()
            self.assertIn("tendencias: 2 activas", out.getvalue())
            with patch("applications.tendencias.servicio.calcular_tendencias", side_effect=RuntimeError("x")):
                err = StringIO()
                call_command("actualizar_noticias", fuente="tn", stdout=StringIO(), stderr=err)
            self.assertIn("no se pudieron calcular", err.getvalue())
