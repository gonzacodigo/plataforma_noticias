from django.contrib import admin
from .models import Noticia, Categoria, NoticiaImagen, ScrapeRun, CopyGenerado, GeneracionIA


class NoticiaImagenInline(admin.TabularInline):
    model = NoticiaImagen
    extra = 0


@admin.register(Noticia)
class NoticiaAdmin(admin.ModelAdmin):
    inlines = [NoticiaImagenInline]
    list_display = ("titulo", "fecha", "categoria", "medio", "fecha_estimada", "solo_tendencias")
    list_filter = ("medio", "categoria", "fecha_estimada", "solo_tendencias")
    search_fields = ("titulo",)
    list_select_related = ("categoria", "medio")
    readonly_fields = ("fecha_ingesta", "actualizado")
    list_per_page = 30


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    search_fields = ("nombre",)


@admin.register(ScrapeRun)
class ScrapeRunAdmin(admin.ModelAdmin):
    list_display = (
        "fuente",
        "inicio",
        "fin",
        "estado",
        "detectadas",
        "guardadas",
        "existentes",
        "omitidas",
    )
    list_filter = ("fuente", "estado")
    readonly_fields = [f.name for f in ScrapeRun._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(GeneracionIA)
class GeneracionIAAdmin(admin.ModelAdmin):
    """Cada llamada real a la API. Las entregas muestran cuántas veces se reutilizó."""

    list_display = ("tipo", "noticia", "tendencia", "modelo", "tokens_entrada", "tokens_salida", "veces_entregada", "creado")
    list_filter = ("tipo", "modelo")
    list_select_related = ("noticia", "tendencia")
    readonly_fields = [f.name for f in GeneracionIA._meta.fields]
    date_hierarchy = "creado"

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).annotate(n_entregas=Count("entregas"))

    @admin.display(description="entregas", ordering="n_entregas")
    def veces_entregada(self, obj):
        return obj.n_entregas

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CopyGenerado)
class CopyGeneradoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "tipo", "noticia", "tendencia", "reutilizada", "editado", "modelo", "tokens_entrada", "tokens_salida", "creado")
    list_filter = ("tipo", "reutilizada", "usuario", "modelo")
    list_select_related = ("usuario", "noticia", "tendencia")
    readonly_fields = [f.name for f in CopyGenerado._meta.fields]
    date_hierarchy = "creado"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.site_header = "Desenchufadas · Administración"
admin.site.site_title = "Desenchufadas"
admin.site.index_title = "Noticias y fuentes"
