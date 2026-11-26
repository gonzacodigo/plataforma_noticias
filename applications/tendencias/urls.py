from django.urls import path
from . import views

app_name = "tendencias"
urlpatterns = [
    path("tendencia/<int:pk>/", views.TendenciaDetalleView.as_view(), name="detalle"),
    path(
        "tendencia/<int:pk>/ia/resumen/",
        views.GenerarResumenTendenciaView.as_view(),
        name="generar_resumen",
    ),
]
