from django.core.management.base import BaseCommand, CommandError
from applications.noticia.services.engine import SOURCES, run_source, ScrapeError


class Command(BaseCommand):
    help = "Actualiza las noticias independientemente de las visitas a la página."

    def add_arguments(self, parser):
        parser.add_argument("--fuente", choices=sorted(SOURCES))
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignorar el resultado reciente de cinco minutos.",
        )

    def handle(self, *args, **options):
        failures = []
        for source in ([options["fuente"]] if options["fuente"] else SOURCES):
            try:
                result = run_source(source, force=options["force"])
                if result["status"] == "partial":
                    failures.append(source)
                self.stdout.write(
                    f"{source}: {result['saved']} guardadas; {result['skipped']} omitidas ({result['status']})"
                )
            except ScrapeError:
                failures.append(source)
                self.stderr.write(
                    f"{source}: no se pudo completar. Revisa el registro de ejecuciones."
                )
        if failures:
            raise CommandError("Fallaron fuentes: " + ", ".join(failures))
