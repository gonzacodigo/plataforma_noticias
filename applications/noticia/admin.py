from django.contrib import admin
from .models import Noticia, Categoria, NoticiaImagen, ScrapeRun


class NoticiaImagenInline(admin.TabularInline):
    model = NoticiaImagen
    extra = 0


@admin.register(Noticia)
class NoticiaAdmin(admin.ModelAdmin):
    inlines = [NoticiaImagenInline]
    list_display = ("titulo", "fecha", "categoria", "medio", "fecha_estimada")
    list_filter = ("medio", "categoria", "fecha_estimada")
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
        "omitidas",
    )
    list_filter = ("fuente", "estado")
    readonly_fields = [f.name for f in ScrapeRun._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.site_header = "Desenchufadas · Administración"
admin.site.site_title = "Desenchufadas"
admin.site.index_title = "Noticias y fuentes"
