from django.contrib import admin
from .models import Noticia, Categoria

# Registrar el modelo Noticia
admin.site.register(Noticia)

# Registrar el modelo Categoria
admin.site.register(Categoria)
