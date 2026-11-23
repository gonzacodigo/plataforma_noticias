from datetime import datetime, time, timedelta
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from applications.noticia.models import CopyGenerado
from .models import Acceso, Cliente, Visita, DIAS_AVISO_VENCIMIENTO

PERIODOS = (7, 30, 90)
SECCIONES = dict(Visita.SECCIONES)
# Más de estas IP distintas en el período sugiere una cuenta compartida.
UMBRAL_IPS = 3
DIAS_INACTIVIDAD = 7


def _periodo(request):
    try:
        dias = int(request.GET.get("dias", 30))
    except ValueError:
        dias = 30
    dias = dias if dias in PERIODOS else 30
    hoy = timezone.localdate()
    desde_fecha = hoy - timedelta(days=dias - 1)
    desde = timezone.make_aware(
        datetime.combine(desde_fecha, time.min)
    )
    return dias, hoy, desde_fecha, desde


def _serie_diaria(visitas, desde_fecha, dias):
    por_dia = {
        fila["dia"]: fila["total"]
        for fila in visitas.annotate(dia=TruncDate("fecha"))
        .values("dia")
        .annotate(total=Count("id"))
    }
    paso = {7: 1, 30: 5, 90: 15}.get(dias, 7)
    serie = []
    for i in range(dias):
        dia = desde_fecha + timedelta(days=i)
        serie.append(
            {
                "etiqueta": dia.strftime("%d/%m"),
                "valor": por_dia.get(dia, 0),
                "mostrar": i % paso == 0 or i == dias - 1,
            }
        )
    return _escalar(serie)


def _serie_horaria(visitas):
    por_hora = {
        fila["hora"]: fila["total"]
        for fila in visitas.annotate(hora=ExtractHour("fecha"))
        .values("hora")
        .annotate(total=Count("id"))
    }
    return _escalar(
        [
            {"etiqueta": f"{h:02d} h", "valor": por_hora.get(h, 0), "mostrar": h % 3 == 0}
            for h in range(24)
        ]
    )


def _por_seccion(visitas):
    filas = [
        {"etiqueta": SECCIONES.get(f["seccion"], f["seccion"]), "valor": f["total"]}
        for f in visitas.values("seccion").annotate(total=Count("id")).order_by("-total")
    ]
    return _escalar(filas)


def _escalar(filas):
    maximo = max((f["valor"] for f in filas), default=0) or 1
    for f in filas:
        f["pct"] = round(f["valor"] * 100 / maximo, 1)
    return filas


def _contexto_base(request, titulo):
    if not request.user.has_perm("cuentas.view_visita"):
        raise PermissionDenied
    return {**admin.site.each_context(request), "title": titulo}


def panel_uso(request):
    contexto = _contexto_base(request, "Panel de uso")
    dias, hoy, desde_fecha, desde = _periodo(request)
    ahora = timezone.now()
    visitas = Visita.objects.filter(fecha__gte=desde)
    inicio_hoy = timezone.make_aware(
        datetime.combine(hoy, time.min)
    )
    User = get_user_model()

    clientes = list(Cliente.objects.annotate(usuarios=Count("perfiles")))
    estados = {"activo": 0, "por_vencer": 0, "vencido": 0, "suspendido": 0}
    for c in clientes:
        estados[c.estado] += 1
    ingreso_mensual = sum(
        (c.precio_mensual or 0) for c in clientes if c.estado in ("activo", "por_vencer")
    )

    copys = CopyGenerado.objects.filter(creado__gte=desde)
    resumen_copys = copys.aggregate(
        total=Count("id"), entrada=Sum("tokens_entrada"), salida=Sum("tokens_salida")
    )

    # Una fila por usuario cliente, incluso sin actividad (riesgo de baja).
    usuarios = (
        User.objects.filter(is_staff=False, is_superuser=False)
        .select_related("perfil__cliente")
        .annotate(
            visitas_periodo=Count("visitas", filter=Q(visitas__fecha__gte=desde)),
            ultima_actividad=Max("visitas__fecha"),
        )
        .order_by("-ultima_actividad", "username")
    )
    detalle = {
        f["usuario"]: f
        for f in visitas.values("usuario").annotate(
            dias_activos=Count(TruncDate("fecha"), distinct=True),
            ips=Count("ip", distinct=True),
            sesiones=Count("sesion", distinct=True),
        )
    }
    favoritas = {}
    for f in (
        visitas.values("usuario", "seccion")
        .annotate(total=Count("id"))
        .order_by("usuario", "-total")
    ):
        favoritas.setdefault(f["usuario"], SECCIONES.get(f["seccion"], f["seccion"]))
    copys_por_usuario = dict(
        copys.values("usuario").annotate(total=Count("id")).values_list("usuario", "total")
    )

    filas, alertas = [], []
    limite_inactivo = ahora - timedelta(days=DIAS_INACTIVIDAD)
    for u in usuarios:
        d = detalle.get(u.pk, {})
        perfil = getattr(u, "perfil", None)
        cliente = perfil.cliente if perfil else None
        fila = {
            "usuario": u,
            "cliente": cliente,
            "ultimo_ingreso": u.last_login,
            "ultima_actividad": u.ultima_actividad,
            "visitas": u.visitas_periodo,
            "dias_activos": d.get("dias_activos", 0),
            "promedio": round(u.visitas_periodo / d["dias_activos"], 1)
            if d.get("dias_activos")
            else 0,
            "favorita": favoritas.get(u.pk, "—"),
            "copys": copys_por_usuario.get(u.pk, 0),
            "ips": d.get("ips", 0),
            "sesiones": d.get("sesiones", 0),
            "compartida": d.get("ips", 0) > UMBRAL_IPS,
            "inactivo": u.is_active
            and (u.ultima_actividad is None or u.ultima_actividad < limite_inactivo),
        }
        filas.append(fila)
        if fila["compartida"]:
            alertas.append(
                ("serious", f"{u.username} usó {fila['ips']} IP distintas: posible cuenta compartida.")
            )
        if fila["inactivo"] and cliente and cliente.acceso_vigente():
            alertas.append(
                ("warning", f"{u.username} ({cliente}) no usa la plataforma hace más de {DIAS_INACTIVIDAD} días.")
            )
        if perfil is None and u.is_active:
            alertas.append(("warning", f"{u.username} no tiene cliente asignado y no puede ingresar."))
    for c in clientes:
        if c.estado == "por_vencer":
            alertas.insert(
                0, ("warning", f"{c.nombre} vence el {c.vencimiento:%d/%m/%Y}.")
            )
        elif c.estado == "vencido":
            alertas.insert(0, ("critical", f"{c.nombre} venció el {c.vencimiento:%d/%m/%Y}."))

    fallidos_24h = Acceso.objects.filter(
        tipo="fallido", fecha__gte=ahora - timedelta(hours=24)
    ).count()
    if fallidos_24h >= 10:
        alertas.append(("critical", f"{fallidos_24h} intentos de ingreso fallidos en 24 horas."))

    total_visitas = visitas.count()
    contexto.update(
        dias=dias,
        periodos=PERIODOS,
        kpis={
            "activos_hoy": Visita.objects.filter(fecha__gte=inicio_hoy)
            .values("usuario")
            .distinct()
            .count(),
            "activos_periodo": visitas.values("usuario").distinct().count(),
            "usuarios_total": len(filas),
            "visitas": total_visitas,
            "visitas_dia": round(total_visitas / dias, 1),
            "copys": resumen_copys["total"],
            "tokens": (resumen_copys["entrada"] or 0) + (resumen_copys["salida"] or 0),
            "ingreso_mensual": ingreso_mensual,
            "fallidos_24h": fallidos_24h,
        },
        estados=estados,
        dias_aviso=DIAS_AVISO_VENCIMIENTO,
        alertas=alertas,
        serie_diaria=_serie_diaria(visitas, desde_fecha, dias),
        serie_horaria=_serie_horaria(visitas),
        secciones=_por_seccion(visitas),
        busquedas=visitas.exclude(busqueda="")
        .values("busqueda")
        .annotate(total=Count("id"), usuarios=Count("usuario", distinct=True))
        .order_by("-total")[:15],
        noticias=visitas.filter(seccion="detalle", noticia__isnull=False)
        .values("noticia__id", "noticia__titulo", "noticia__medio__nombre")
        .annotate(total=Count("id"), usuarios=Count("usuario", distinct=True))
        .order_by("-total")[:10],
        medios=_escalar(
            [
                {"etiqueta": f["noticia__medio__nombre"], "valor": f["total"]}
                for f in visitas.filter(seccion="detalle", noticia__isnull=False)
                .values("noticia__medio__nombre")
                .annotate(total=Count("id"))
                .order_by("-total")[:8]
            ]
        ),
        dispositivos=visitas.exclude(dispositivo="")
        .values("dispositivo")
        .annotate(total=Count("id"))
        .order_by("-total"),
        filas=filas,
    )
    return render(request, "admin/cuentas/panel.html", contexto)


def panel_usuario(request, pk):
    User = get_user_model()
    usuario = get_object_or_404(User.objects.select_related("perfil__cliente"), pk=pk)
    contexto = _contexto_base(request, f"Actividad de {usuario.username}")
    dias, hoy, desde_fecha, desde = _periodo(request)
    visitas = Visita.objects.filter(usuario=usuario, fecha__gte=desde)
    resumen = visitas.aggregate(
        total=Count("id"),
        dias_activos=Count(TruncDate("fecha"), distinct=True),
        ips=Count("ip", distinct=True),
        sesiones=Count("sesion", distinct=True),
    )
    copys = CopyGenerado.objects.filter(usuario=usuario, creado__gte=desde)
    contexto.update(
        dias=dias,
        periodos=PERIODOS,
        usuario_obj=usuario,
        cliente=getattr(getattr(usuario, "perfil", None), "cliente", None),
        resumen=resumen,
        copys_total=copys.count(),
        serie_diaria=_serie_diaria(visitas, desde_fecha, dias),
        serie_horaria=_serie_horaria(visitas),
        secciones=_por_seccion(visitas),
        busquedas=visitas.exclude(busqueda="")
        .values("busqueda")
        .annotate(total=Count("id"))
        .order_by("-total")[:10],
        conexiones=visitas.values("ip", "dispositivo", "navegador")
        .annotate(total=Count("id"), ultima=Max("fecha"))
        .order_by("-ultima")[:15],
        recientes=Visita.objects.filter(usuario=usuario)
        .select_related("noticia")
        .order_by("-fecha")[:50],
        accesos=Acceso.objects.filter(
            Q(usuario=usuario) | Q(usuario__isnull=True, nombre_usuario=usuario.username)
        ).order_by("-fecha")[:20],
        ultimos_copys=copys.select_related("noticia")[:10],
    )
    return render(request, "admin/cuentas/usuario.html", contexto)
