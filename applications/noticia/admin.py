from django.contrib import admin
from .models import Noticia, Categoria, NoticiaImagen


class NoticiaImagenInline(admin.TabularInline):
    model = NoticiaImagen
    extra = 0

class NoticiaAdmin(admin.ModelAdmin):
    inlines = [NoticiaImagenInline]
    list_display = ('titulo', 'fecha', 'categoria', 'medio')


admin.site.register(Noticia, NoticiaAdmin)
admin.site.register(Categoria)
