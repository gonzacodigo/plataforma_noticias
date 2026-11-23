from datetime import timedelta
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from .models import Acceso, Cliente, Perfil, Visita

ESTADOS = {
    "activo": ("#0ca30c", "Activo"),
    "por_vencer": ("#fab219", "Vence pronto"),
    "vencido": ("#d03b3b", "Vencido"),
    "suspendido": ("#d03b3b", "Suspendido"),
}


def estado_html(cliente):
    color, texto = ESTADOS[cliente.estado]
    return format_html(
        '<span style="display:inline-flex;align-items:center;gap:6px">'
        '<span aria-hidden="true" style="width:10px;height:10px;border-radius:50%;background:{}"></span>{}</span>',
        color,
        texto,
    )


class PerfilFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        vigentes = [
            f for f in self.forms
            if f.cleaned_data and not f.cleaned_data.get("DELETE")
        ]
        maximo = self.instance.max_usuarios
        if len(vigentes) > maximo:
            raise ValidationError(
                f"El plan permite {maximo} usuario(s) y cargaste {len(vigentes)}. "
                "Subí el máximo de usuarios o quitá alguno."
            )


class PerfilClienteInline(admin.TabularInline):
    model = Perfil
    formset = PerfilFormSet
    extra = 0
    autocomplete_fields = ["usuario"]
    verbose_name = "usuario"
    verbose_name_plural = "Usuarios con acceso"


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    inlines = [PerfilClienteInline]
    list_display = (
        "nombre", "estado_col", "plan", "vencimiento", "usuarios_col",
        "precio_mensual", "sesion_unica",
    )
    list_filter = ("activo", "plan", "sesion_unica")
    search_fields = ("nombre", "contacto", "email")
    actions = ["extender_30", "suspender", "reactivar"]
    fieldsets = (
        (None, {"fields": ("nombre", "contacto", "email", "telefono")}),
        ("Suscripción", {"fields": ("plan", "precio_mensual", "activo", "vencimiento")}),
        ("Límites", {"fields": ("max_usuarios", "limite_copys_mensual", "sesion_unica")}),
        ("Notas internas", {"fields": ("notas",), "classes": ("collapse",)}),
    )

    @admin.display(description="Estado")
    def estado_col(self, obj):
        return estado_html(obj)

    @admin.display(description="Usuarios")
    def usuarios_col(self, obj):
        return f"{obj.perfiles.count()} / {obj.max_usuarios}"

    @admin.action(description="Extender 30 días la suscripción")
    def extender_30(self, request, queryset):
        hoy = timezone.localdate()
        for c in queryset:
            base = c.vencimiento if c.vencimiento and c.vencimiento >= hoy else hoy
            c.vencimiento = base + timedelta(days=30)
            c.activo = True
            c.save(update_fields=["vencimiento", "activo"])
        self.message_user(request, f"Se extendieron {queryset.count()} suscripción(es).")

    @admin.action(description="Suspender acceso")
    def suspender(self, request, queryset):
        n = queryset.update(activo=False)
        self.message_user(request, f"{n} cliente(s) suspendido(s).", messages.WARNING)

    @admin.action(description="Reactivar acceso")
    def reactivar(self, request, queryset):
        n = queryset.update(activo=True)
        self.message_user(request, f"{n} cliente(s) reactivado(s).")


class PerfilUsuarioInline(admin.StackedInline):
    model = Perfil
    can_delete = False
    verbose_name = "cliente"
    verbose_name_plural = "Cliente al que pertenece"
    fields = ("cliente",)


User = get_user_model()
admin.site.unregister(User)


@admin.register(User)
class UsuarioAdmin(UserAdmin):
    inlines = [PerfilUsuarioInline]
    list_display = (
        "username", "first_name", "last_name", "cliente_col", "is_active",
        "last_login", "actividad",
    )
    list_select_related = ("perfil__cliente",)
    list_filter = ("is_active", "is_staff", "perfil__cliente")

    @admin.display(description="Cliente", ordering="perfil__cliente__nombre")
    def cliente_col(self, obj):
        perfil = getattr(obj, "perfil", None)
        return perfil.cliente if perfil else "—"

    @admin.display(description="Uso")
    def actividad(self, obj):
        return format_html(
            '<a href="{}">Ver actividad</a>', reverse("panel_usuario", args=[obj.pk])
        )


class SoloLecturaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Visita)
class VisitaAdmin(SoloLecturaAdmin):
    list_display = ("fecha", "usuario", "seccion", "ruta", "busqueda", "dispositivo", "navegador", "ip")
    list_filter = ("seccion", "dispositivo", "usuario__perfil__cliente")
    search_fields = ("usuario__username", "busqueda", "ruta", "ip")
    list_select_related = ("usuario",)
    date_hierarchy = "fecha"
    list_per_page = 50


@admin.register(Acceso)
class AccesoAdmin(SoloLecturaAdmin):
    list_display = ("fecha", "tipo", "nombre_usuario", "ip", "dispositivo", "navegador", "detalle")
    list_filter = ("tipo", "dispositivo")
    search_fields = ("nombre_usuario", "ip")
    date_hierarchy = "fecha"
    list_per_page = 50
