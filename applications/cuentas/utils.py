import hashlib
import ipaddress
import logging
import re
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# url_name de noticia_app -> sección registrada.
SECCION_POR_VISTA = {
    "inicio": "noticias",
    "noticia_categoria": "categoria",
    "noticia_medio": "medio",
    "noticia_detail": "detalle",
    "generar_copy": "copy_ia",
    "instagram": "comunidad",
    "buscador_imagenes": "imagenes",
}
FILTROS = ("categoria", "categorias", "medio", "fecha1", "fecha2", "page")


def client_ip(request):
    """IP del visitante. Detrás de nginx se toma de la cabecera que él fija."""
    header = getattr(settings, "ACTIVIDAD_IP_HEADER", "")
    value = request.META.get(header, "") if header else ""
    value = value or request.META.get("REMOTE_ADDR", "")
    value = value.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def describir_agente(user_agent):
    ua = user_agent or ""
    if re.search(r"iPad|Tablet", ua) or ("Android" in ua and "Mobile" not in ua):
        dispositivo = "tablet"
    elif re.search(r"Mobi|iPhone|Android", ua):
        dispositivo = "celular"
    elif ua:
        dispositivo = "escritorio"
    else:
        dispositivo = ""
    for patron, nombre in (
        (r"Edg/", "Edge"),
        (r"OPR/|Opera", "Opera"),
        (r"SamsungBrowser", "Samsung"),
        (r"Firefox/|FxiOS", "Firefox"),
        (r"Chrome/|CriOS", "Chrome"),
        (r"Safari/", "Safari"),
    ):
        if re.search(patron, ua):
            navegador = nombre
            break
    else:
        navegador = "Otro" if ua else ""
    for patron, nombre in (
        (r"iPhone|iPad|iOS", "iOS"),
        (r"Android", "Android"),
        (r"Windows", "Windows"),
        (r"Mac OS X|Macintosh", "macOS"),
        (r"Linux", "Linux"),
    ):
        if re.search(patron, ua):
            navegador = f"{navegador} · {nombre}"
            break
    return dispositivo, navegador[:60]


def huella_sesion(session_key, largo=64):
    if not session_key:
        return ""
    return hashlib.sha256(session_key.encode()).hexdigest()[:largo]


def datos_cliente(request):
    dispositivo, navegador = describir_agente(request.META.get("HTTP_USER_AGENT"))
    return {"ip": client_ip(request), "dispositivo": dispositivo, "navegador": navegador}


def perfil_de(user):
    from .models import Perfil

    if not getattr(user, "is_authenticated", False):
        return None
    cache = getattr(user, "_perfil_cache", False)
    if cache is False:
        cache = Perfil.objects.select_related("cliente").filter(usuario=user).first()
        user._perfil_cache = cache
    return cache


def motivo_bloqueo(user, request=None):
    """Devuelve por qué el usuario no puede usar la plataforma, o None."""
    if not user.is_active:
        return "Tu usuario está desactivado."
    if user.is_staff or user.is_superuser:
        return None
    perfil = perfil_de(user)
    if perfil is None:
        return "Tu cuenta no tiene un cliente asignado. Contactá al administrador."
    cliente = perfil.cliente
    if not cliente.activo:
        return "El acceso de tu cuenta está suspendido. Contactá al administrador."
    if not cliente.acceso_vigente():
        return "La suscripción de tu cuenta venció. Contactá al administrador para renovarla."
    if (
        request is not None
        and cliente.sesion_unica
        and perfil.sesion_actual
        and perfil.sesion_actual != huella_sesion(request.session.session_key)
    ):
        return "Se cerró tu sesión porque tu cuenta ingresó desde otro dispositivo."
    return None


def limite_copys(user):
    perfil = perfil_de(user)
    if perfil and perfil.cliente.limite_copys_mensual is not None:
        return perfil.cliente.limite_copys_mensual
    return settings.COPY_IA_LIMITE_MENSUAL


def registrar_acceso(request, tipo, usuario=None, nombre="", detalle=""):
    from .models import Acceso

    try:
        Acceso.objects.create(
            usuario=usuario,
            nombre_usuario=(nombre or getattr(usuario, "username", ""))[:150],
            tipo=tipo,
            detalle=detalle[:200],
            **datos_cliente(request),
        )
    except Exception:
        logger.exception("No se pudo registrar el acceso")


def registrar_visita(request, response):
    from .models import Visita

    user = request.user
    match = request.resolver_match
    if (
        not user.is_authenticated
        or response.status_code != 200
        or match is None
        or match.namespace != "noticia_app"
        or match.url_name not in SECCION_POR_VISTA
    ):
        return
    if (user.is_staff or user.is_superuser) and not settings.ACTIVIDAD_REGISTRAR_STAFF:
        return
    seccion = SECCION_POR_VISTA[match.url_name]
    if (seccion == "copy_ia") != (request.method == "POST"):
        return
    busqueda = request.GET.get("kword", "").strip()[:200]
    if busqueda and seccion == "noticias":
        seccion = "busqueda"
    filtros = {
        k: ",".join(request.GET.getlist(k))[:100]
        for k in FILTROS
        if request.GET.get(k)
    }
    noticia_id = match.kwargs.get("pk") if seccion in ("detalle", "copy_ia") else None
    try:
        Visita.objects.create(
            usuario=user,
            fecha=timezone.now(),
            seccion=seccion,
            ruta=request.path[:300],
            noticia_id=noticia_id,
            busqueda=busqueda,
            filtros=filtros,
            sesion=huella_sesion(request.session.session_key, 16),
            **datos_cliente(request),
        )
    except Exception:
        logger.exception("No se pudo registrar la visita")
