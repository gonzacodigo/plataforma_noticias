from django.apps import AppConfig


class CuentasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "applications.cuentas"
    verbose_name = "Clientes y actividad"

    def ready(self):
        from . import signals  # noqa: F401
