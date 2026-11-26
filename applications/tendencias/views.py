from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView
from applications.noticia import herramientas_ia
from .models import Tendencia


class TendenciaDetalleView(DetailView):
    """Cómo contó la historia cada medio (solo para clientes, ver middleware)."""

    template_name = "tendencias/detalle.html"
    context_object_name = "tendencia"

    def get_queryset(self):
        return Tendencia.objects.filter(oculta=False).select_related("categoria")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["noticias"] = (
            self.object.noticias.select_related("medio", "categoria")
            .defer("contenido")
            .order_by("fecha", "fecha_ingesta", "id")
        )
        tendencia = self.object
        context.update(
            herramientas_ia.contexto(
                self.request.user,
                ("resumen_tendencia",),
                lambda tipo: reverse("tendencias:generar_resumen", args=[tendencia.pk]),
                tendencia=tendencia,
            )
        )
        return context


class GenerarResumenTendenciaView(LoginRequiredMixin, View):
    """Resumen de varias fuentes: herramienta paga (cuenta para el límite)."""

    http_method_names = ["post"]
    raise_exception = True

    def post(self, request, pk):
        tendencia = get_object_or_404(Tendencia, pk=pk, oculta=False)
        return herramientas_ia.responder(request, "resumen_tendencia", tendencia=tendencia)
