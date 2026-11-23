from django.core.management.base import BaseCommand
from applications.tendencias.servicio import calcular_tendencias


class Command(BaseCommand):
    help = "Recalcula las noticias en tendencia (también corre al final de actualizar_noticias)."

    def handle(self, *args, **options):
        r = calcular_tendencias()
        self.stdout.write(
            f"Tendencias: {r['activas']} activas ({r['nuevas']} nuevas) "
            f"sobre {r['notas_analizadas']} notas."
        )
