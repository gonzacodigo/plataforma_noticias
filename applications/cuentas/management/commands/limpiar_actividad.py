from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from applications.cuentas.models import Acceso, Visita


class Command(BaseCommand):
    help = "Borra visitas e ingresos más viejos que el período de retención."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias", type=int, default=settings.ACTIVIDAD_RETENCION_DIAS
        )

    def handle(self, *args, dias, **options):
        limite = timezone.now() - timedelta(days=dias)
        visitas, _ = Visita.objects.filter(fecha__lt=limite).delete()
        accesos, _ = Acceso.objects.filter(fecha__lt=limite).delete()
        self.stdout.write(
            f"Borradas {visitas} visitas y {accesos} ingresos anteriores a {dias} días."
        )
