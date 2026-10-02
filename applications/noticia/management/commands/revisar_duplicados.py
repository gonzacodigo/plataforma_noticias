from django.core.management.base import BaseCommand
from django.db.models import Count
from applications.noticia.models import Noticia, NoticiaImagen
from applications.medio.models import Medio


class Command(BaseCommand):
    help = "Informa duplicados; no modifica ni elimina datos."

    def handle(self, *args, **kwargs):
        groups = {}
        for pk, name in Medio.objects.values_list("pk", "nombre"):
            groups.setdefault(name.strip().upper(), []).append(pk)
        for name, ids in groups.items():
            if len(ids) > 1:
                self.stdout.write(f"Medios {name}: IDs {ids}")
        for row in (
            Noticia.objects.exclude(url="")
            .values("medio_id", "url")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        ):
            self.stdout.write(
                f"Noticias medio={row['medio_id']} cantidad={row['n']} URL={row['url']}"
            )
        for row in (
            NoticiaImagen.objects.values("noticia_id", "url")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        ):
            self.stdout.write(
                f"Imágenes noticia={row['noticia_id']} cantidad={row['n']}"
            )
