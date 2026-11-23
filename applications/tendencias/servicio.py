import logging
from collections import Counter
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from applications.noticia.models import Categoria, Noticia
from .models import Tendencia
from .motor import agrupar, puntaje

logger = logging.getLogger(__name__)


def calcular_tendencias(ahora=None):
    """Recalcula las tendencias activas a partir de las notas de la ventana.

    Conserva la misma tendencia (y su enlace) mientras el tema siga vivo: un
    grupo nuevo se asocia a la tendencia activa con la que comparte más notas.
    """
    ahora = ahora or timezone.now()
    desde = ahora - timedelta(hours=settings.TENDENCIAS_VENTANA_HORAS)
    notas = list(
        Noticia.objects.filter(fecha_ingesta__gte=desde, fecha_ingesta__lte=ahora)
        .exclude(titulo="")
        .select_related("medio")
        .only(
            "id", "titulo", "descripcion", "medio_id", "medio__nombre", "categoria_id",
            "fecha", "fecha_ingesta",
        )
    )
    nombres = dict(Categoria.objects.values_list("id", "nombre"))
    grupos = []
    for grupo in agrupar(notas, umbral=settings.TENDENCIAS_UMBRAL):
        primera, categoria_id = _primera_y_categoria(grupo)
        # Espectáculos tiene menos medios que lo cubren; el resto (General) exige más.
        minimo = (
            settings.TENDENCIAS_MIN_MEDIOS
            if "ESPECTACULO" in nombres.get(categoria_id, "")
            else settings.TENDENCIAS_MIN_MEDIOS_GENERAL
        )
        if len({n.medio_id for n in grupo}) >= minimo:
            grupos.append((grupo, primera, categoria_id))
    lecturas = _lecturas_de_clientes(desde, [n.id for g, _, _ in grupos for n in g])

    activas = {
        t.pk: t for t in Tendencia.objects.filter(activa=True).prefetch_related("noticias")
    }
    tendencia_de_nota = {
        nota_id: pk for pk, t in activas.items() for nota_id in (n.pk for n in t.noticias.all())
    }

    vigentes, nuevas = set(), 0
    with transaction.atomic():
        for grupo, primera, categoria_id in sorted(grupos, key=lambda g: len(g[0]), reverse=True):
            ids = {n.id for n in grupo}
            coincidencias = Counter(
                tendencia_de_nota[i] for i in ids if i in tendencia_de_nota
            )
            pk = next((pk for pk, _ in coincidencias.most_common() if pk not in vigentes), None)
            medios = sorted({n.medio.nombre for n in grupo})
            # La recencia del puntaje usa la descarga (confiable); lo visible, la publicación.
            ultima = max(n.fecha_ingesta for n in grupo)
            leidas = sum(lecturas.get(i, 0) for i in ids)
            campos = {
                "categoria_id": categoria_id,
                "titulo": primera.titulo[:500],
                "nota_principal_id": primera.id,
                "medios": medios,
                "cantidad_medios": len(medios),
                "cantidad_notas": len(grupo),
                "lecturas": leidas,
                "puntaje": puntaje(
                    len(medios),
                    len(grupo),
                    (ahora - ultima).total_seconds() / 3600,
                    leidas,
                ),
                "primera_aparicion": primera.fecha,
                "ultima_aparicion": max(n.fecha for n in grupo),
            }
            if pk:
                tendencia = activas[pk]
                for campo, valor in campos.items():
                    setattr(tendencia, campo, valor)
                tendencia.save()
            else:
                tendencia = Tendencia.objects.create(**campos)
                nuevas += 1
            tendencia.noticias.set(ids)
            vigentes.add(tendencia.pk)
        Tendencia.objects.filter(activa=True).exclude(pk__in=vigentes).update(activa=False)
    return {"activas": len(vigentes), "nuevas": nuevas, "notas_analizadas": len(notas)}


def _primera_y_categoria(grupo):
    """La primera nota es la que un medio publicó antes: de ella sale el título.

    La categoría es la más repetida en el grupo; ante un empate, la de la primera.
    """
    primera = min(grupo, key=lambda n: (n.fecha, n.fecha_ingesta, n.id))
    categorias = Counter(n.categoria_id for n in grupo)
    return primera, max(categorias, key=lambda c: (categorias[c], c == primera.categoria_id))


def _lecturas_de_clientes(desde, noticia_ids):
    if not noticia_ids:
        return {}
    from applications.cuentas.models import Visita

    return dict(
        Visita.objects.filter(seccion="detalle", fecha__gte=desde, noticia_id__in=noticia_ids)
        .values_list("noticia_id")
        .annotate(total=Count("id"))
        .values_list("noticia_id", "total")
    )


def es_espectaculos(categoria):
    return "ESPECTACULO" in categoria.nombre


def top_por_categoria(cantidad=None):
    """Dos apartados: Espectáculos y General (todas las demás categorías juntas).

    Devuelve [(etiqueta, tendencias)] con las mejores de cada apartado y omite
    el que no tenga tendencias.
    """
    cantidad = cantidad or settings.TENDENCIAS_POR_CATEGORIA
    apartados = {"Espectáculos": [], "General": []}
    for tendencia in (
        Tendencia.objects.filter(activa=True, oculta=False)
        .select_related("categoria")
        .order_by("-puntaje", "-ultima_aparicion")
    ):
        lista = apartados["Espectáculos" if es_espectaculos(tendencia.categoria) else "General"]
        if len(lista) < cantidad:
            lista.append(tendencia)
    return [(etiqueta, lista) for etiqueta, lista in apartados.items() if lista]
