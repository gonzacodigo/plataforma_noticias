from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from applications.medio.models import Medio
from applications.noticia.models import Categoria, CopyGenerado, Noticia
from .models import Acceso, Cliente, Perfil, Visita
from .utils import describir_agente

User = get_user_model()
UA_CELULAR = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36"
)


def crear_usuario(username="ana", cliente=None, **cliente_kwargs):
    user = User.objects.create_user(username, password="clave-segura-123")
    cliente = cliente or Cliente.objects.create(nombre=f"Cliente {username}", **cliente_kwargs)
    Perfil.objects.create(usuario=user, cliente=cliente)
    return user


def ingresar(client, username="ana", password="clave-segura-123", **extra):
    return client.post(
        "/ingresar/", {"username": username, "password": password}, **extra
    )


class BaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.noticia = Noticia.objects.create(
            titulo="Estreno de la temporada",
            fecha=timezone.now(),
            medio=Medio.objects.create(nombre="TN"),
            categoria=Categoria.objects.create(nombre="ESPECTACULOS"),
            url="https://tn.com.ar/show/estreno/",
        )

    def setUp(self):
        cache.clear()


class LoginObligatorioTests(BaseTests):
    def test_anonimo_ve_el_listado_de_noticias(self):
        for url in ["/", "/?kword=Estreno", "/noticia-medio/", "/noticia-categoria/", "/instagram-views"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.get("/")
        self.assertContains(response, "Estreno de la temporada")
        self.assertContains(response, "Ingresá para leer")
        self.assertContains(response, self.noticia.get_absolute_url())
        self.assertFalse(Visita.objects.exists())

    def test_anonimo_necesita_cuenta_para_leer_e_imagenes(self):
        for url in [self.noticia.get_absolute_url(), "/buscador-imagenes"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(
                    response, f"/ingresar/?next={url}", fetch_redirect_response=False
                )
        response = self.client.get(f"/ingresar/?next={self.noticia.get_absolute_url()}")
        self.assertContains(response, "Para leer la noticia completa necesitás una cuenta.")

    def test_ingresar_desde_una_noticia_vuelve_a_ella(self):
        crear_usuario()
        url = self.noticia.get_absolute_url()
        response = self.client.post(
            "/ingresar/",
            {"username": "ana", "password": "clave-segura-123", "next": url},
        )
        self.assertRedirects(response, url)
        self.assertContains(self.client.get("/"), "Leer noticia")

    def test_404_sigue_siendo_404(self):
        self.assertEqual(self.client.get("/no-existe/").status_code, 404)

    def test_post_anonimo_es_rechazado(self):
        url = f"/detail-noticia/{self.noticia.pk}/generar-copy/"
        self.assertEqual(self.client.post(url).status_code, 403)

    def test_rutas_publicas(self):
        self.assertEqual(self.client.get("/ingresar/").status_code, 200)
        self.assertEqual(self.client.get("/salud/").status_code, 200)
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)

    def test_menu_segun_sesion(self):
        response = self.client.get("/")
        self.assertContains(response, ">Ingresar</a>")
        self.assertNotContains(response, "/buscador-imagenes")
        self.client.force_login(crear_usuario())
        response = self.client.get("/")
        self.assertContains(response, "/buscador-imagenes")
        self.assertContains(response, "Salir")

    def test_usuario_bloqueado_en_la_vidriera_es_desconectado(self):
        user = crear_usuario(activo=False)
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertRedirects(response, "/ingresar/?next=/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/ingresar/").status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_cliente_vigente_ingresa(self):
        crear_usuario()
        response = ingresar(self.client)
        self.assertRedirects(response, "/")
        self.assertContains(self.client.get("/"), "Salir")

    def test_usuario_sin_cliente_no_ingresa(self):
        User.objects.create_user("suelto", password="clave-segura-123")
        response = ingresar(self.client, "suelto")
        self.assertContains(response, "no tiene un cliente asignado")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_staff_sin_cliente_ingresa(self):
        User.objects.create_user("jefe", password="clave-segura-123", is_staff=True)
        self.assertRedirects(ingresar(self.client, "jefe"), "/")

    def test_cliente_vencido_o_suspendido_no_ingresa(self):
        ayer = timezone.localdate() - timedelta(days=1)
        crear_usuario("vencido", vencimiento=ayer)
        crear_usuario("suspendido", activo=False)
        self.assertContains(ingresar(self.client, "vencido"), "venció")
        self.assertContains(ingresar(self.client, "suspendido"), "suspendido")

    def test_vence_hoy_todavia_tiene_acceso(self):
        crear_usuario(vencimiento=timezone.localdate())
        self.assertRedirects(ingresar(self.client), "/")

    def test_suspender_corta_la_sesion_abierta(self):
        user = crear_usuario()
        self.client.force_login(user)
        self.assertEqual(self.client.get("/").status_code, 200)
        user.perfil.cliente.activo = False
        user.perfil.cliente.save()
        response = self.client.get("/")
        self.assertRedirects(response, "/ingresar/?next=/", fetch_redirect_response=False)
        self.assertContains(self.client.get(response["Location"]), "suspendido")
        self.assertTrue(Acceso.objects.filter(tipo="bloqueado", usuario=user).exists())

    def test_sesion_unica_cierra_el_otro_dispositivo(self):
        crear_usuario(sesion_unica=True)
        pc, celular = Client(), Client()
        ingresar(pc)
        self.assertEqual(pc.get("/").status_code, 200)
        ingresar(celular)
        self.assertEqual(celular.get("/").status_code, 200)
        response = pc.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertContains(pc.get(response["Location"]), "otro dispositivo")

    def test_sin_sesion_unica_conviven_dispositivos(self):
        crear_usuario()
        pc, celular = Client(), Client()
        ingresar(pc)
        ingresar(celular)
        self.assertEqual(pc.get("/").status_code, 200)
        self.assertEqual(celular.get("/").status_code, 200)

    def test_bloqueo_tras_intentos_fallidos(self):
        crear_usuario()
        for _ in range(5):
            self.assertContains(ingresar(self.client, password="mala"), "incorrectos")
        response = ingresar(self.client)
        self.assertContains(response, "Demasiados intentos")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_salir_lleva_al_login(self):
        self.client.force_login(crear_usuario())
        self.assertRedirects(self.client.post("/salir/"), "/ingresar/")


class RegistroActividadTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.user = crear_usuario()
        self.client.force_login(self.user)

    def test_registra_secciones(self):
        for url in [
            "/",
            "/noticia-medio/",
            "/noticia-categoria/",
            "/instagram-views",
            "/buscador-imagenes",
            self.noticia.get_absolute_url(),
        ]:
            self.client.get(url)
        self.assertEqual(
            sorted(Visita.objects.values_list("seccion", flat=True)),
            sorted(["noticias", "medio", "categoria", "comunidad", "imagenes", "detalle"]),
        )
        detalle = Visita.objects.get(seccion="detalle")
        self.assertEqual(detalle.noticia, self.noticia)
        self.assertEqual(detalle.usuario, self.user)

    def test_registra_busqueda_filtros_y_dispositivo(self):
        self.client.get(
            "/",
            {"kword": "  Wanda  ", "page": "1"},
            HTTP_USER_AGENT=UA_CELULAR,
            REMOTE_ADDR="203.0.113.7",
        )
        visita = Visita.objects.get()
        self.assertEqual(visita.seccion, "busqueda")
        self.assertEqual(visita.busqueda, "Wanda")
        self.assertEqual(visita.filtros, {"page": "1"})
        self.assertEqual(visita.dispositivo, "celular")
        self.assertEqual(visita.navegador, "Chrome · Android")
        self.assertEqual(visita.ip, "203.0.113.7")
        self.assertTrue(visita.sesion)

    @override_settings(ACTIVIDAD_IP_HEADER="HTTP_X_REAL_IP")
    def test_ip_desde_el_proxy(self):
        self.client.get("/", HTTP_X_REAL_IP="198.51.100.4", REMOTE_ADDR="")
        self.assertEqual(Visita.objects.get().ip, "198.51.100.4")

    def test_no_registra_errores_ni_redirecciones(self):
        self.client.get("/detail-noticia/999999/")
        self.client.get("/", {"fecha1": "invalida"})
        self.assertEqual(Visita.objects.filter(seccion="detalle").count(), 0)

    def test_registra_copy_ia(self):
        resultado = {"texto": "Copy", "modelo": "m", "tokens_entrada": 1, "tokens_salida": 1}
        with patch("applications.noticia.views.generar_copy", return_value=resultado):
            self.client.post(f"/detail-noticia/{self.noticia.pk}/generar-copy/")
        self.assertTrue(Visita.objects.filter(seccion="copy_ia", noticia=self.noticia).exists())

    def test_staff_no_se_registra(self):
        staff = User.objects.create_user("jefe", password="x", is_staff=True)
        self.client.force_login(staff)
        self.client.get("/")
        self.assertFalse(Visita.objects.filter(usuario=staff).exists())

    def test_falla_del_registro_no_rompe_el_sitio(self):
        with patch.object(Visita.objects, "create", side_effect=RuntimeError("db")):
            self.assertEqual(self.client.get("/").status_code, 200)


class AccesosTests(BaseTests):
    def test_registra_ingreso_salida_y_fallido(self):
        user = crear_usuario()
        ingresar(self.client, password="mala", HTTP_USER_AGENT=UA_CELULAR)
        ingresar(self.client)
        self.client.post("/salir/")
        tipos = list(Acceso.objects.order_by("fecha", "id").values_list("tipo", "nombre_usuario"))
        self.assertEqual(tipos, [("fallido", "ana"), ("login", "ana"), ("logout", "ana")])
        self.assertEqual(Acceso.objects.get(tipo="fallido").dispositivo, "celular")
        self.assertEqual(Acceso.objects.get(tipo="login").usuario, user)


class LimiteCopysTests(BaseTests):
    @override_settings(COPY_IA_HABILITADO=True, COPY_IA_LIMITE_MENSUAL=3)
    def test_limite_propio_del_cliente(self):
        user = crear_usuario(limite_copys_mensual=1)
        self.client.force_login(user)
        url = f"/detail-noticia/{self.noticia.pk}/generar-copy/"
        resultado = {"texto": "Copy", "modelo": "m", "tokens_entrada": 1, "tokens_salida": 1}
        with patch("applications.noticia.views.generar_copy", return_value=resultado):
            respuestas = [self.client.post(url) for _ in range(2)]
        self.assertEqual([r.status_code for r in respuestas], [200, 429])
        self.assertEqual(respuestas[0].json()["restantes"], 0)
        self.assertContains(self.client.get(self.noticia.get_absolute_url()), "Te quedan 0")


class ClienteTests(BaseTests):
    def test_estados(self):
        hoy = timezone.localdate()
        casos = {
            "activo": Cliente(nombre="a"),
            "por_vencer": Cliente(nombre="b", vencimiento=hoy + timedelta(days=3)),
            "vencido": Cliente(nombre="c", vencimiento=hoy - timedelta(days=1)),
            "suspendido": Cliente(nombre="d", activo=False),
        }
        for esperado, cliente in casos.items():
            self.assertEqual(cliente.estado, esperado)

    def test_maximo_de_usuarios(self):
        cliente = Cliente.objects.create(nombre="Agencia", max_usuarios=1)
        crear_usuario("uno", cliente=cliente)
        perfil = Perfil(usuario=User.objects.create_user("dos"), cliente=cliente)
        with self.assertRaises(ValidationError):
            perfil.full_clean()

    def test_no_se_borra_cliente_con_usuarios(self):
        from django.db.models.deletion import ProtectedError

        user = crear_usuario()
        with self.assertRaises(ProtectedError):
            user.perfil.cliente.delete()

    def test_describir_agente(self):
        self.assertEqual(describir_agente(UA_CELULAR), ("celular", "Chrome · Android"))
        self.assertEqual(
            describir_agente("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36 Edg/130.0"),
            ("escritorio", "Edge · Windows"),
        )
        self.assertEqual(describir_agente(""), ("", ""))


class PanelTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("admin", password="x")
        self.ana = crear_usuario(vencimiento=timezone.localdate() + timedelta(days=2))
        self.ana.perfil.cliente.precio_mensual = 25000
        self.ana.perfil.cliente.save()
        lector = Client()
        lector.force_login(self.ana)
        lector.get("/", {"kword": "Wanda"})
        lector.get(self.noticia.get_absolute_url())
        CopyGenerado.objects.create(usuario=self.ana, noticia=self.noticia, texto="t", modelo="m")
        crear_usuario("dormido")

    def test_requiere_staff_con_permiso(self):
        self.assertEqual(self.client.get("/admin/panel/").status_code, 302)
        staff = User.objects.create_user("editor", password="x", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/admin/panel/").status_code, 403)

    def test_panel_muestra_metricas_y_alertas(self):
        self.client.force_login(self.admin)
        for dias in ("7", "30", "90", "basura"):
            with self.subTest(dias=dias):
                response = self.client.get("/admin/panel/", {"dias": dias})
                self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["dias"], 30)
        kpis = response.context["kpis"]
        self.assertEqual((kpis["activos_hoy"], kpis["visitas"], kpis["copys"]), (1, 2, 1))
        self.assertEqual(kpis["ingreso_mensual"], 25000)
        self.assertContains(response, "Wanda")
        self.assertContains(response, "Estreno de la temporada")
        self.assertContains(response, "Cliente ana vence el")
        self.assertContains(response, "dormido (Cliente dormido) no usa la plataforma")
        fila = next(f for f in response.context["filas"] if f["usuario"] == self.ana)
        self.assertEqual((fila["visitas"], fila["dias_activos"], fila["copys"]), (2, 1, 1))
        self.assertEqual(fila["favorita"] in ("Búsqueda", "Lectura de noticia"), True)

    def test_detalle_de_usuario(self):
        self.client.force_login(self.admin)
        response = self.client.get(f"/admin/panel/usuario/{self.ana.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["resumen"]["total"], 2)
        self.assertContains(response, "Lectura de noticia")
        self.assertEqual(self.client.get("/admin/panel/usuario/999999/").status_code, 404)

    def test_admin_de_clientes_y_actividad(self):
        self.client.force_login(self.admin)
        for url in [
            "/admin/",
            "/admin/cuentas/cliente/",
            f"/admin/cuentas/cliente/{self.ana.perfil.cliente.pk}/change/",
            "/admin/cuentas/visita/",
            "/admin/cuentas/acceso/",
            "/admin/auth/user/",
            f"/admin/auth/user/{self.ana.pk}/change/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get("/admin/"), "Panel de uso")

    def test_accion_extender_suscripcion(self):
        self.client.force_login(self.admin)
        cliente = self.ana.perfil.cliente
        vencimiento = cliente.vencimiento
        self.client.post(
            "/admin/cuentas/cliente/",
            {"action": "extender_30", "_selected_action": [cliente.pk]},
        )
        cliente.refresh_from_db()
        self.assertEqual(cliente.vencimiento, vencimiento + timedelta(days=30))


class LimpiezaTests(BaseTests):
    def test_borra_actividad_vieja(self):
        user = crear_usuario()
        vieja = timezone.now() - timedelta(days=400)
        Visita.objects.create(usuario=user, seccion="noticias", ruta="/", fecha=vieja)
        Visita.objects.create(usuario=user, seccion="noticias", ruta="/")
        Acceso.objects.create(tipo="login", nombre_usuario="ana", fecha=vieja)
        call_command("limpiar_actividad", stdout=StringIO())
        self.assertEqual(Visita.objects.count(), 1)
        self.assertEqual(Acceso.objects.count(), 0)
