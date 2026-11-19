from concurrent.futures import ThreadPoolExecutor
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections
from applications.noticia.services.engine import SOURCES, run_source, ScrapeError


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
        parser.add_argument("--fuente", choices=sorted(SOURCES))
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
        for source in [options["fuente"]] if options["fuente"] else SOURCES:
            groups.setdefault(SOURCES[source][0], []).append(source)
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
        if failures:
            raise CommandError("Fallaron fuentes: " + ", ".join(failures))
