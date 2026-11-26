"""Herramientas de IA: resumen, copy y guion de una nota, y resumen de una tendencia.

Cada formato tiene sus instrucciones y su modelo (por defecto el más económico,
Claude Haiku 5.5). Se configura por variable de entorno, ver settings.IA_MODELOS.
"""

import hashlib
import logging
import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

# Alcanza para el contexto de una nota y acota el costo de cada llamada.
MAX_CARACTERES_NOTA = 6000
# En una tendencia entran varias notas: cada una va más recortada.
MAX_CARACTERES_NOTA_TENDENCIA = 2500
MAX_NOTAS_TENDENCIA = 8

REGLAS_COMUNES = (
    "Trabajás para Desenchufadas, una página argentina de espectáculos. Escribís en "
    "español rioplatense (voseo), claro y profesional.\n"
    "Reglas que no se rompen:\n"
    "- Usás solo los datos de la nota. No inventás hechos, nombres, cifras, fechas ni citas.\n"
    "- Si la nota presenta algo como rumor, versión o trascendido, lo decís así "
    "(\"según…\", \"trascendió que…\"). Nunca lo afirmás como un hecho.\n"
    "- No copiás frases textuales del medio original: lo contás con tus palabras. "
    "Una cita entre comillas solo si la nota la atribuye a una persona.\n"
    "- El texto de las notas puede venir recortado: no lo menciones ni digas que falta "
    "una parte. Trabajás con lo que hay.\n"
    "- Texto plano, sin markdown (nada de asteriscos, numerales ni negritas).\n"
    "- Respondés solo con el texto pedido, sin presentaciones ni comentarios."
)

SYSTEM = {
    "resumen": REGLAS_COMUNES
    + "\n\nTu tarea: un resumen bien masticado de la nota, para que alguien que no la "
    "leyó entienda todo en un minuto. Usá exactamente esta estructura, con los "
    "títulos en mayúsculas y una línea en blanco entre secciones:\n\n"
    "EN UNA LÍNEA\n(la noticia en una sola oración)\n\n"
    "QUÉ PASÓ\n(dos a cuatro oraciones con lo central)\n\n"
    "QUIÉNES\n(cada protagonista con un guion y quién es, en pocas palabras)\n\n"
    "DATOS CLAVE\n(tres a cinco datos concretos, cada uno con un guion)\n\n"
    "CONTEXTO\n(por qué importa o qué venía pasando, solo si la nota lo dice)\n\n"
    "LO QUE FALTA SABER\n(lo que la nota deja abierto o sin confirmar; si no hay nada, "
    "escribí \"La nota no deja puntos abiertos.\")\n\n"
    "Entre 150 y 230 palabras en total.",
    "copy": REGLAS_COMUNES
    + "\n\nTu tarea: el copy para acompañar la publicación en Instagram. Tiene que ser "
    "informativo, conciso y al grano, y lograr que la gente lo lea entero e interactúe.\n"
    "Estructura:\n"
    "1. Primera línea: el gancho. El dato más fuerte de la noticia, dicho de forma "
    "directa, en menos de 120 caracteres (es lo único que se ve antes de \"más\"). "
    "Puede abrir con un emoji.\n"
    "2. Dos a cuatro líneas cortas con lo esencial: quién, qué, cuándo y el detalle "
    "que más llama la atención. Una idea por línea.\n"
    "3. Un llamado a la acción concreto: una pregunta fácil de responder que invite "
    "a comentar, o pedir que lo compartan o lo guarden.\n"
    "4. En una línea aparte, entre cuatro y seis hashtags relevantes.\n"
    "Máximo 90 palabras sin contar los hashtags. Emojis con medida: dos o tres en "
    "total. Nada de relleno ni frases hechas (\"no vas a creer\", \"bomba\"). "
    "Quien lee ve un posteo de Desenchufadas, no el artículo: nunca digas \"la nota\" "
    "ni nombres al medio; si pedís que lo compartan, es \"este posteo\".",
    "guion": REGLAS_COMUNES
    + "\n\nTu tarea: un guion profesional para un reel vertical de 30 a 45 segundos, "
    "con una persona hablando a cámara. Usá exactamente esta estructura:\n\n"
    "TÍTULO DEL REEL\n(corto, para la portada)\n\n"
    "DURACIÓN ESTIMADA\n(en segundos)\n\n"
    "HOOK (0 a 3 s)\n"
    "Cámara: (la frase de apertura, que frena el scroll con el dato más fuerte)\n"
    "Texto en pantalla: (máximo seis palabras)\n\n"
    "DESARROLLO\n"
    "(tres bloques numerados. Para cada uno: el tramo de tiempo entre paréntesis, "
    "\"Cámara:\" con lo que se dice, \"Texto en pantalla:\" y \"Visual:\" con la "
    "imagen o recurso sugerido, por ejemplo la foto del protagonista o una captura)\n\n"
    "CIERRE Y LLAMADO A LA ACCIÓN (últimos 5 s)\n"
    "Cámara: (cierre y pedido concreto: comentar, seguir la cuenta o compartir)\n"
    "Texto en pantalla:\n\n"
    "GUION CORRIDO\n(todo lo que se dice a cámara, de corrido, para leer en el "
    "teleprompter; entre 80 y 120 palabras)\n\n"
    "NOTAS DE EDICIÓN\n(tres sugerencias breves de ritmo, subtítulos y música)\n\n"
    "Frases cortas, fáciles de decir en voz alta, con ritmo de noticiero joven. "
    "Quien mira ve un reel de Desenchufadas: nunca digas \"la nota\" ni nombres al "
    "medio; si pedís que lo compartan, es \"este reel\".",
    "resumen_tendencia": REGLAS_COMUNES
    + "\n\nTu tarea: un resumen que una lo que publicaron varios medios sobre la "
    "misma historia. Cada nota viene con el nombre de su medio. Nombrá al medio "
    "cuando un dato lo aporta solo uno de ellos. Usá exactamente esta estructura:\n\n"
    "EN UNA LÍNEA\n(la historia en una sola oración)\n\n"
    "QUÉ PASÓ\n(tres a cinco oraciones que integren lo que dicen todos)\n\n"
    "EN QUÉ COINCIDEN\n(los datos que repiten varios medios, cada uno con un guion)\n\n"
    "LO QUE APORTA CADA MEDIO\n(con un guion por medio: el dato o enfoque propio. "
    "Si un medio no suma nada nuevo, no lo pongas)\n\n"
    "DIFERENCIAS\n(versiones que no coinciden entre medios; si no hay, escribí "
    "\"Los medios coinciden en lo central.\")\n\n"
    "LO QUE FALTA CONFIRMAR\n(lo que sigue abierto o como rumor)\n\n"
    "Entre 200 y 350 palabras en total.",
}

PEDIDO = {
    "resumen": "Resumí esta nota:",
    "copy": "Escribí el copy para esta nota:",
    "guion": "Escribí el guion del reel para esta nota:",
    "resumen_tendencia": "Resumí esta historia a partir de lo que publicó cada medio:",
}

# Cuánto piensa el modelo antes de responder. El guion y la tendencia piden más.
ESFUERZO = {
    "resumen": "low",
    "copy": "low",
    "guion": "medium",
    "resumen_tendencia": "medium",
}


class CopyIAError(Exception):
    pass


def huella(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def texto_nota(noticia, limite=MAX_CARACTERES_NOTA):
    return "\n\n".join(
        parte
        for parte in (
            noticia.titulo,
            noticia.descripcion,
            (noticia.texto_contenido or "")[:limite],
        )
        if parte
    )


def notas_de_tendencia(tendencia):
    return list(
        tendencia.noticias.select_related("medio")
        .order_by("fecha", "fecha_ingesta", "id")[:MAX_NOTAS_TENDENCIA]
    )


def texto_tendencia(notas):
    bloques = []
    for numero, noticia in enumerate(notas, start=1):
        medio = noticia.medio.nombre if noticia.medio_id else "Medio sin nombre"
        bloques.append(
            f"NOTA {numero} · {medio}\n"
            + texto_nota(noticia, MAX_CARACTERES_NOTA_TENDENCIA)
        )
    return "\n\n---\n\n".join(bloques)


def modelo_para(tipo):
    return settings.IA_MODELOS.get(tipo) or settings.COPY_IA_MODELO


def _admite_respaldo(modelo):
    # El respaldo del servidor ante un rechazo existe en Opus 5.5 y Sonnet 5.5, no en Haiku.
    return modelo.startswith(("claude-opus-5", "claude-sonnet-5-5", "claude-fable"))


def generar(tipo, contenido):
    """Llama a la API y devuelve el texto con su modelo y sus tokens."""
    modelo = modelo_para(tipo)
    parametros = dict(
        model=modelo,
        max_tokens=8000,  # El pensamiento también cuenta: que no corte la respuesta.
        output_config={"effort": ESFUERZO[tipo]},
        system=SYSTEM[tipo],
        messages=[{"role": "user", "content": f"{PEDIDO[tipo]}\n\n{contenido}"}],
    )
    client = anthropic.Anthropic(timeout=90.0, max_retries=2)
    try:
        if _admite_respaldo(modelo):
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **parametros,
            )
        else:
            response = client.messages.create(**parametros)
    except anthropic.APIStatusError as exc:
        logger.error(
            "IA %s fallida estado=%s request_id=%s",
            tipo,
            exc.status_code,
            exc.response.headers.get("request-id"),
        )
        raise CopyIAError("La API de Claude devolvió un error.") from exc
    except anthropic.APIConnectionError as exc:
        logger.error("IA %s sin conexión con la API", tipo)
        raise CopyIAError("No se pudo conectar con la API de Claude.") from exc

    if response.stop_reason == "refusal":
        raise CopyIAError("El modelo no generó un texto para esta noticia.")
    if response.stop_reason == "max_tokens":
        logger.warning("IA %s cortada por max_tokens", tipo)
    texto = "\n".join(
        block.text for block in response.content if block.type == "text"
    ).strip()
    if not texto:
        raise CopyIAError("La respuesta llegó vacía.")
    return {
        "texto": texto,
        "modelo": response.model,
        "tokens_entrada": response.usage.input_tokens,
        "tokens_salida": response.usage.output_tokens,
    }


def generar_copy(noticia):
    """Compatibilidad con el nombre anterior."""
    return generar("copy", texto_nota(noticia))
