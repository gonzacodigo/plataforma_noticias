"""Reparte generaciones de IA entre clientes para pagar una sola llamada por nota.

Si otro cliente ya generó el mismo formato para el mismo contenido, se entrega
esa generación (la pantalla igual muestra la animación de "generando"). Con
``nueva=True`` (el botón "Generar otra versión") siempre se llama a la API.
Las dos formas cuentan para el límite mensual del cliente.
"""

from ..models import CopyGenerado, GeneracionIA
from . import ia

TIPOS_NOTICIA = ("resumen", "copy", "guion")


def _contenido_y_huella(tipo, noticia, tendencia):
    if tipo == "resumen_tendencia":
        notas = ia.notas_de_tendencia(tendencia)
        ids = ",".join(str(n.pk) for n in sorted(notas, key=lambda n: n.pk))
        return ia.texto_tendencia(notas), ia.huella(ids)
    contenido = ia.texto_nota(noticia)
    return contenido, ia.huella(contenido)


def huella_actual(tipo, noticia=None, tendencia=None):
    return _contenido_y_huella(tipo, noticia, tendencia)[1]


def entregar(usuario, tipo, *, noticia=None, tendencia=None, nueva=False):
    """Devuelve el CopyGenerado del usuario. Puede lanzar ia.CopyIAError."""
    contenido, huella = _contenido_y_huella(tipo, noticia, tendencia)
    generacion = None
    if not nueva:
        recibidas = CopyGenerado.objects.filter(
            usuario=usuario, generacion__isnull=False
        ).values("generacion_id")
        generacion = (
            GeneracionIA.objects.filter(
                tipo=tipo, noticia=noticia, tendencia=tendencia, huella=huella
            )
            .exclude(pk__in=recibidas)
            .order_by("-creado")
            .first()
        )
    reutilizada = generacion is not None
    if generacion is None:
        resultado = ia.generar(tipo, contenido)
        generacion = GeneracionIA.objects.create(
            tipo=tipo, noticia=noticia, tendencia=tendencia, huella=huella, **resultado
        )
    return CopyGenerado.objects.create(
        usuario=usuario,
        tipo=tipo,
        noticia=noticia,
        tendencia=tendencia,
        generacion=generacion,
        reutilizada=reutilizada,
        texto=generacion.texto,
        modelo=generacion.modelo,
        # Una entrega reutilizada no consumió tokens.
        tokens_entrada=0 if reutilizada else generacion.tokens_entrada,
        tokens_salida=0 if reutilizada else generacion.tokens_salida,
    )


def ultima_entrega(usuario, tipo, *, noticia=None, tendencia=None):
    return (
        CopyGenerado.objects.filter(
            usuario=usuario, tipo=tipo, noticia=noticia, tendencia=tendencia
        )
        .select_related("generacion")
        .order_by("-creado")
        .first()
    )
