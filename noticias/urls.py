from django.contrib import admin
from django.http import JsonResponse
from django.db import connection
from django.urls import path, include
from django.views.decorators.http import require_GET
from applications.cuentas.panel import panel_uso, panel_usuario


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
    path("", include("applications.noticia.urls")),
]
