from django.contrib import admin
from django.http import HttpResponse, HttpResponsePermanentRedirect, JsonResponse
from django.db import connection
from django.templatetags.static import static
from django.urls import path, include
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET
from applications.cuentas.panel import panel_uso, panel_usuario

# Las notas completas, el copy y las herramientas piden cuenta: que los
# buscadores no gasten visitas ahí. Crawl-delay frena a los bots que lo
# respetan (ClaudeBot hacía 15 mil pedidos por día).
ROBOTS_TXT = """User-agent: *
Disallow: /admin/
Disallow: /api/
Disallow: /ingresar/
Disallow: /salir/
Disallow: /detail-noticia/
Disallow: /tendencia/
Disallow: /buscador-imagenes
Disallow: /*?*page=
Crawl-delay: 10
"""


@require_GET
@cache_control(public=True, max_age=86400)
def robots_txt(request):
    return HttpResponse(ROBOTS_TXT, content_type="text/plain; charset=utf-8")


@require_GET
def favicon(request):
    # Los navegadores y bots piden /favicon.ico aunque la página declare el SVG.
    return HttpResponsePermanentRedirect(static("img/brand-mark.svg"))


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)


urlpatterns = [
    path("admin/panel/", admin.site.admin_view(panel_uso), name="panel_uso"),
    path(
        "admin/panel/usuario/<int:pk>/",
        admin.site.admin_view(panel_usuario),
        name="panel_usuario",
    ),
    path("admin/", admin.site.urls),
    path("salud/", health, name="health"),
    path("robots.txt", robots_txt, name="robots"),
    path("favicon.ico", favicon, name="favicon"),
    path("", include("applications.tendencias.urls")),
    path("", include("applications.noticia.urls")),
]
