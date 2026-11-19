"""Generación de copys para redes sociales con la API de Claude."""

import logging
import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

# Alcanza para el contexto de la nota y acota el costo de cada copy.
MAX_CARACTERES_NOTA = 4000

SYSTEM = (
    "Sos community manager de una página de espectáculos argentina. "
    "Escribís copys para Instagram con tono cercano y rioplatense. "
    "Usás solo los datos de la nota: no inventás hechos, nombres ni citas, "
    "y no copiás frases textuales del medio original. "
    "Respondés solo con el copy listo para pegar, en texto plano sin markdown: "
    "dos o tres oraciones, una pregunta para invitar a comentar y, en una línea "
    "aparte, cinco hashtags."
)


class CopyIAError(Exception):
    pass


def generar_copy(noticia):
    nota = "\n\n".join(
        parte
        for parte in (
            noticia.titulo,
            noticia.descripcion,
            noticia.texto_contenido[:MAX_CARACTERES_NOTA],
        )
        if parte
    )
    client = anthropic.Anthropic(timeout=60.0, max_retries=2)
    try:
        response = client.beta.messages.create(
            model=settings.COPY_IA_MODELO,
            max_tokens=2000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},
            system=SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"Escribí el copy para esta noticia:\n\n{nota}",
                }
            ],
        )
    except anthropic.APIStatusError as exc:
        logger.error(
            "Copy IA fallido estado=%s request_id=%s",
            exc.status_code,
            exc.response.headers.get("request-id"),
        )
        raise CopyIAError("La API de Claude devolvió un error.") from exc
    except anthropic.APIConnectionError as exc:
        logger.error("Copy IA sin conexión con la API")
        raise CopyIAError("No se pudo conectar con la API de Claude.") from exc

    if response.stop_reason == "refusal":
        raise CopyIAError("El modelo no generó un copy para esta noticia.")
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
