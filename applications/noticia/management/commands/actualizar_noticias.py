from concurrent.futures import ThreadPoolExecutor
import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections
from applications.noticia.services.engine import SOURCES, run_source, ScrapeError
from applications.noticia.services.feeds import FEEDS

logger = logging.getLogger(__name__)


def run_group(sources, force):
    """Fuentes de un mismo medio, en orden: comparten el bloqueo del medio."""
    results = []
    for source in sources:
        try:
            results.append((source, run_source(source, force=force)))
        except ScrapeError:
            results.append((source, None))
    return results


def run_group_in_thread(sources, force):
    try:
        return run_group(sources, force)
    finally:
        # Cada hilo abre su propia conexión a la base.
        connections.close_all()


class Command(BaseCommand):
    help = "Actualiza las noticias independientemente de las visitas a la página."

    def add_arguments(self, parser):
        parser.add_argument("--fuente", choices=sorted([*SOURCES, *FEEDS]))
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignorar el resultado reciente de cinco minutos.",
        )
        parser.add_argument(
            "--paralelo",
            type=int,
            help="Medios procesados a la vez (por defecto 4; 1 con SQLite).",
        )

    def handle(self, *args, **options):
        groups = {}
        for source in [options["fuente"]] if options["fuente"] else [*SOURCES, *FEEDS]:
            medio = SOURCES[source][0] if source in SOURCES else FEEDS[source]["medio"]
            groups.setdefault(medio, []).append(source)
        workers = options["paralelo"] or (1 if connection.vendor == "sqlite" else 4)
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                batches = list(
                    pool.map(
                        lambda group: run_group_in_thread(group, options["force"]),
                        groups.values(),
                    )
                )
        else:
            batches = [run_group(group, options["force"]) for group in groups.values()]
        failures = []
        for source, result in (item for batch in batches for item in batch):
            if result is None:
                failures.append(source)
                self.stderr.write(
                    f"{source}: no se pudo completar. Revisa el registro de ejecuciones."
                )
                continue
            if result["status"] == "partial":
                failures.append(source)
            self.stdout.write(
                f"{source}: {result['saved']} guardadas; {result.get('known', 0)} ya existentes; "
                f"{result['skipped']} omitidas ({result['status']})"
            )
        self.actualizar_tendencias()
        self.podar()
        if failures:
            raise CommandError("Fallaron fuentes: " + ", ".join(failures))

    def actualizar_tendencias(self):
        from applications.tendencias.servicio import calcular_tendencias

        try:
            r = calcular_tendencias()
        except Exception:
            # Las tendencias nunca deben frenar la ingesta de noticias.
            logger.exception("No se pudieron calcular las tendencias")
            self.stderr.write("tendencias: no se pudieron calcular. Revisa el registro.")
            return
        self.stdout.write(f"tendencias: {r['activas']} activas ({r['nuevas']} nuevas)")

    def podar(self):
        from applications.noticia.services.limpieza import podar_noticias

        try:
            r = podar_noticias()
        except Exception:
            # La poda tampoco debe frenar la ingesta: se reintenta en la próxima corrida.
            logger.exception("No se pudo podar la tabla de noticias")
            self.stderr.write("poda: no se pudo completar. Revisa el registro.")
            return
        if r["borradas"]:
            self.stdout.write(
                f"poda: {r['borradas']} noticias viejas borradas"
                + ("" if r["completa"] else " (sigue en la próxima corrida)")
            )
