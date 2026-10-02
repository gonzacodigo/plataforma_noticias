from django.contrib import admin
from django.http import JsonResponse
from django.db import connection
from django.urls import path, include
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("salud/", health, name="health"),
    path("", include("applications.noticia.urls")),
]
