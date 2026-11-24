"""Poda automática: evita que la tabla de noticias crezca sin límite.

Cuando hay NOTICIAS_MAXIMO notas o más, borra las más viejas (por fecha de
publicación) hasta dejar NOTICIAS_CONSERVAR. Se borran también sus imágenes y
sus enlaces históricos; las visitas, los copys y las tendencias se conservan sin
el enlace a la nota. Las notas de tendencias activas nunca se borran.

Cada corrida borra como mucho durante NOTICIAS_PODA_SEGUNDOS. Si no termina,
deja una marca y la próxima corrida sigue hasta llegar a NOTICIAS_CONSERVAR.
"""

import logging
import time
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from applications.noticia.models import Noticia, NoticiaAlias

logger = logging.getLogger(__name__)
LOTE = 1000
MARCA_PENDIENTE = "poda-noticias-pendiente"


def notas_protegidas():
    from applications.tendencias.models import Tendencia

    return Tendencia.noticias.through.objects.filter(
        tendencia__activa=True
    ).values("noticia_id")


def podar_noticias(maximo=None, conservar=None, simular=False, lote=LOTE, segundos=None):
    maximo = settings.NOTICIAS_MAXIMO if maximo is None else maximo
    conservar = settings.NOTICIAS_CONSERVAR if conservar is None else conservar
    segundos = settings.NOTICIAS_PODA_SEGUNDOS if segundos is None else segundos
    if not 0 < conservar < maximo:
        raise ValueError("NOTICIAS_CONSERVAR tiene que ser mayor que 0 y menor que NOTICIAS_MAXIMO.")

    total = Noticia.objects.count()
    resultado = {
        "total": total, "borradas": 0, "hasta": None, "simulado": simular, "completa": True
    }
    pendiente = cache.get(MARCA_PENDIENTE, False)
    if total < maximo and not (pendiente and total > conservar):
        if pendiente:
            cache.delete(MARCA_PENDIENTE)
        return resultado

    ids = list(
        Noticia.objects.exclude(pk__in=notas_protegidas())
        .order_by("fecha", "id")
        .values_list("pk", flat=True)[: total - conservar]
    )
    if ids:
        resultado["hasta"] = Noticia.objects.filter(pk=ids[-1]).values_list("fecha", flat=True).first()
    if simular:
        resultado["borradas"] = len(ids)
        return resultado

    limite = time.monotonic() + segundos
    for inicio in range(0, len(ids), lote):
        if inicio and time.monotonic() >= limite:
            resultado["completa"] = False
            break
        tanda = ids[inicio : inicio + lote]
        with transaction.atomic():
            # Los alias protegen a la nota: van primero.
            NoticiaAlias.objects.filter(noticia_id__in=tanda).delete()
            _, detalle = Noticia.objects.filter(pk__in=tanda).delete()
        resultado["borradas"] += detalle.get("noticia.Noticia", 0)

    if resultado["completa"]:
        cache.delete(MARCA_PENDIENTE)
    else:
        cache.set(MARCA_PENDIENTE, True, None)
    logger.info(
        "Poda de noticias: %s borradas (publicadas hasta %s); quedan %s%s",
        resultado["borradas"],
        resultado["hasta"],
        total - resultado["borradas"],
        "" if resultado["completa"] else "; sigue en la próxima corrida",
    )
    return resultado
