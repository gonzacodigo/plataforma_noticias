from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.urls import Resolver404, resolve
from .utils import motivo_bloqueo, registrar_acceso, registrar_visita

# Vistas que cualquiera puede ver: el listado de noticias funciona como vidriera.
# Leer cada noticia, el copy con IA y el buscador de imágenes exigen cuenta.
VISTAS_PUBLICAS = {
    "noticia_app:inicio",
    "noticia_app:noticia_categoria",
    "noticia_app:noticia_medio",
    "noticia_app:instagram",
    "noticia_app:ingresar",
    "noticia_app:salir",
    "health",
    "robots",
    "favicon",
}
RUTAS_PUBLICAS = (
    "/static/",
    "/media/",
    "/admin/",  # El admin tiene su propio login.
    "/api/",  # La API exige administrador y responde 403.
)


def es_publica(path):
    if path.startswith(RUTAS_PUBLICAS):
        return True
    try:
        match = resolve(path)
    except Resolver404:
        return True  # Que responda el 404 habitual.
    return match.view_name in VISTAS_PUBLICAS


class AccesoClientesMiddleware:
    """Exige login fuera de la vidriera, valida la suscripción y registra el uso."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        publica = es_publica(request.path_info)
        if user.is_authenticated and not request.path_info.startswith(
            RUTAS_PUBLICAS + ("/ingresar/", "/salir/")
        ):
            motivo = motivo_bloqueo(user, request)
            if motivo:
                registrar_acceso(request, "bloqueado", user, detalle=motivo)
                request._sin_registro_salida = True
                logout(request)
                messages.error(request, motivo)
                if request.method in ("GET", "HEAD"):
                    return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
                return HttpResponseForbidden()
        elif not user.is_authenticated and not publica:
            if request.method in ("GET", "HEAD"):
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            return HttpResponseForbidden()
        response = self.get_response(request)
        registrar_visita(request, response)
        return response
