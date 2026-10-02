from django.contrib import admin
from .models import Medio


@admin.register(Medio)
class MedioAdmin(admin.ModelAdmin):
    search_fields = ("nombre",)
    list_display = ("nombre", "categoria")
