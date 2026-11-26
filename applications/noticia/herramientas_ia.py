"""Vistas y contexto de las herramientas de IA (notas y tendencias)."""

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views import View
from applications.cuentas.utils import limite_copys
from .models import CopyGenerado, Noticia
from .services import entregas
from .services.ia import CopyIAError

MAX_CARACTERES_EDICION = 12000

HERRAMIENTAS = {
    "resumen": {
        "titulo": "Resumen",
        "descripcion": "La nota masticada: qué pasó, quiénes, los datos clave y lo que falta saber.",
        "generar": "Generar resumen",
        "filas": 14,
    },
    "copy": {
        "titulo": "Copy para redes",
        "descripcion": "Texto para Instagram, informativo y al grano, con llamado a la acción y hashtags.",
        "generar": "Generar copy",
        "filas": 9,
    },
    "guion": {
        "titulo": "Guion para reel",
        "descripcion": "Guion de 30 a 45 segundos: hook, desarrollo, llamado a la acción, versión para teleprompter y notas de edición.",
        "generar": "Generar guion",
        "filas": 22,
    },
    "resumen_tendencia": {
        "titulo": "Resumen de la tendencia",
        "descripcion": "Todo lo que publicaron los medios sobre esta historia en un solo texto: en qué coinciden, qué aporta cada uno y qué falta confirmar.",
        "generar": "Generar resumen de la tendencia",
        "filas": 18,
    },
}


def restantes(usuario):
    return max(0, limite_copys(usuario) - CopyGenerado.usados_este_mes(usuario))


def contexto(usuario, tipos, url_generar, *, noticia=None, tendencia=None):
    """Lo que necesita templates/includes/herramientas_ia.html."""
    if not settings.COPY_IA_HABILITADO:
        return {"ia_habilitada": False}
    if not usuario.is_authenticated:
        return {"ia_habilitada": True}
    herramientas = []
    for tipo in tipos:
        entrega = entregas.ultima_entrega(usuario, tipo, noticia=noticia, tendencia=tendencia)
        desactualizada = bool(
            entrega
            and tipo == "resumen_tendencia"
            and (
                entrega.generacion is None
                or entrega.generacion.huella
                != entregas.huella_actual(tipo, tendencia=tendencia)
            )
        )
        herramientas.append(
            {
                "tipo": tipo,
                **HERRAMIENTAS[tipo],
                "url": url_generar(tipo),
                "entrega": entrega,
                "guardar_url": reverse("noticia_app:guardar_ia", args=[entrega.pk])
                if entrega
                else "",
                "desactualizada": desactualizada,
            }
        )
    return {
        "ia_habilitada": True,
        "herramientas_ia": herramientas,
        "ia_restantes": restantes(usuario),
    }


def responder(request, tipo, *, noticia=None, tendencia=None):
    if not settings.COPY_IA_HABILITADO:
        return JsonResponse(
            {"error": "Las herramientas de IA no están disponibles."}, status=503
        )
    if restantes(request.user) <= 0:
        return JsonResponse(
            {"error": "Alcanzaste el límite de generaciones de este mes."}, status=429
        )
    nueva = request.POST.get("nueva") == "1"
    try:
        entrega = entregas.entregar(
            request.user, tipo, noticia=noticia, tendencia=tendencia, nueva=nueva
        )
    except CopyIAError:
        return JsonResponse(
            {"error": "No se pudo generar el texto. Probá de nuevo en un rato."},
            status=502,
        )
    return JsonResponse(
        {
            "texto": entrega.texto,
            "copy": entrega.texto,  # Nombre anterior, por si quedó una página vieja abierta.
            "guardar_url": reverse("noticia_app:guardar_ia", args=[entrega.pk]),
            "restantes": restantes(request.user),
        }
    )


class GenerarIANoticiaView(LoginRequiredMixin, View):
    http_method_names = ["post"]
    raise_exception = True

    def post(self, request, pk, tipo="copy"):
        if tipo not in entregas.TIPOS_NOTICIA:
            raise Http404
        noticia = get_object_or_404(Noticia, pk=pk)
        return responder(request, tipo, noticia=noticia)


class GuardarIAView(LoginRequiredMixin, View):
    """Guarda los cambios que el usuario le hizo a su texto."""

    http_method_names = ["post"]
    raise_exception = True

    def post(self, request, pk):
        entrega = get_object_or_404(CopyGenerado, pk=pk, usuario=request.user)
        texto = request.POST.get("texto", "").strip()
        if not texto:
            return JsonResponse({"error": "El texto no puede quedar vacío."}, status=400)
        if len(texto) > MAX_CARACTERES_EDICION:
            return JsonResponse({"error": "El texto es demasiado largo."}, status=400)
        entrega.texto = texto
        entrega.editado = timezone.now()
        entrega.save(update_fields=["texto", "editado"])
        return JsonResponse({"ok": True})
