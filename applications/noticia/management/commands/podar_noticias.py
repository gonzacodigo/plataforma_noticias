from django.core.management.base import BaseCommand
from applications.noticia.services.limpieza import podar_noticias


class Command(BaseCommand):
    help = (
        "Si hay NOTICIAS_MAXIMO noticias o más, borra las más viejas hasta dejar "
        "NOTICIAS_CONSERVAR. Corre sola al final de actualizar_noticias."
    )

    def add_arguments(self, parser):
        parser.add_argument("--simular", action="store_true", help="Mostrar qué borraría, sin borrar.")
        parser.add_argument("--maximo", type=int, help="Reemplaza NOTICIAS_MAXIMO.")
        parser.add_argument("--conservar", type=int, help="Reemplaza NOTICIAS_CONSERVAR.")

    def handle(self, *args, **options):
        r = podar_noticias(options["maximo"], options["conservar"], simular=options["simular"])
        if not r["borradas"]:
            self.stdout.write(f"poda: {r['total']} noticias, no hace falta borrar.")
            return
        verbo = "borraría" if r["simulado"] else "borró"
        hasta = f"{r['hasta']:%d/%m/%Y}" if r["hasta"] else "-"
        self.stdout.write(
            f"poda: {verbo} {r['borradas']} noticias (publicadas hasta el {hasta}); "
            f"quedan {r['total'] - r['borradas']}."
            + ("" if r["completa"] else " Se acabó el tiempo: sigue en la próxima corrida.")
        )
