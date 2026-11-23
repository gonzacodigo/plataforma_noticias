from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from .models import Tendencia


@admin.register(Tendencia)
class TendenciaAdmin(admin.ModelAdmin):
    list_display = (
        "titulo", "categoria", "cantidad_medios", "cantidad_notas", "lecturas",
        "puntaje", "ultima_aparicion", "activa", "oculta",
    )
    list_editable = ("oculta",)
    list_filter = ("activa", "oculta", "categoria")
    search_fields = ("titulo",)
    list_select_related = ("categoria",)
    date_hierarchy = "primera_aparicion"
    fields = (
        "titulo", "categoria", "oculta", "activa", "medios_col", "cantidad_notas",
        "lecturas", "puntaje", "primera_aparicion", "ultima_aparicion", "notas_col",
    )
    readonly_fields = [f for f in fields if f != "oculta"]
    actions = ["ocultar", "mostrar"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="Medios")
    def medios_col(self, obj):
        return ", ".join(obj.medios)

    @admin.display(description="Notas agrupadas")
    def notas_col(self, obj):
        notas = obj.noticias.select_related("medio").order_by("fecha")
        return format_html(
            "<ol style='margin:0;padding-left:18px'>{}</ol>",
            format_html_join(
                "",
                "<li><b>{}</b> · {} · <a href='{}' target='_blank' rel='noopener'>{}</a></li>",
                (
                    (n.medio.nombre, timezone.localtime(n.fecha).strftime("%d/%m %H:%M"), n.get_absolute_url(), n.titulo)
                    for n in notas
                ),
            ),
        )

    @admin.action(description="Ocultar las tendencias seleccionadas")
    def ocultar(self, request, queryset):
        self.message_user(request, f"{queryset.update(oculta=True)} tendencia(s) ocultas.")

    @admin.action(description="Volver a mostrar las tendencias seleccionadas")
    def mostrar(self, request, queryset):
        self.message_user(request, f"{queryset.update(oculta=False)} tendencia(s) visibles.")
