from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

DIAS_AVISO_VENCIMIENTO = 7


class Cliente(models.Model):
    """Quien alquila la plataforma. Puede tener uno o varios usuarios."""

    PLANES = [
        ("prueba", "Prueba"),
        ("mensual", "Mensual"),
        ("anual", "Anual"),
        ("personalizado", "Personalizado"),
    ]
    nombre = models.CharField(max_length=150, unique=True)
    contacto = models.CharField("persona de contacto", max_length=150, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField("teléfono", max_length=40, blank=True)
    plan = models.CharField(max_length=20, choices=PLANES, default="mensual")
    precio_mensual = models.DecimalField(
        "precio mensual", max_digits=12, decimal_places=2, null=True, blank=True
    )
    activo = models.BooleanField(
        default=True,
        help_text="Desmarcar suspende el acceso de todos sus usuarios de inmediato.",
    )
    vencimiento = models.DateField(
        null=True,
        blank=True,
        help_text="Último día con acceso. Vacío: sin vencimiento.",
    )
    max_usuarios = models.PositiveSmallIntegerField("máximo de usuarios", default=1)
    limite_copys_mensual = models.PositiveIntegerField(
        "límite de copys IA por usuario y mes",
        null=True,
        blank=True,
        help_text="Vacío: usa el límite general del sitio.",
    )
    sesion_unica = models.BooleanField(
        "sesión única",
        default=False,
        help_text="Cada usuario puede tener una sola sesión abierta: al ingresar "
        "desde otro dispositivo se cierra la anterior. Evita compartir la cuenta.",
    )
    notas = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def acceso_vigente(self, hoy=None):
        hoy = hoy or timezone.localdate()
        return self.activo and (self.vencimiento is None or self.vencimiento >= hoy)

    @property
    def estado(self):
        hoy = timezone.localdate()
        if not self.activo:
            return "suspendido"
        if self.vencimiento and self.vencimiento < hoy:
            return "vencido"
        if self.vencimiento and self.vencimiento <= hoy + timedelta(
            days=DIAS_AVISO_VENCIMIENTO
        ):
            return "por_vencer"
        return "activo"


class Perfil(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil"
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="perfiles"
    )
    # Hash de la sesión vigente, para "sesión única".
    sesion_actual = models.CharField(max_length=64, blank=True, editable=False)

    class Meta:
        verbose_name = "usuario del cliente"
        verbose_name_plural = "usuarios del cliente"

    def __str__(self):
        return f"{self.usuario} · {self.cliente}"

    def clean(self):
        if not self.cliente_id:
            return
        otros = Perfil.objects.filter(cliente_id=self.cliente_id).exclude(pk=self.pk)
        if otros.count() >= self.cliente.max_usuarios:
            raise ValidationError(
                f"{self.cliente} ya tiene {self.cliente.max_usuarios} usuario(s), "
                "el máximo de su plan."
            )


class Visita(models.Model):
    SECCIONES = [
        ("noticias", "Noticias"),
        ("busqueda", "Búsqueda"),
        ("categoria", "Por categoría"),
        ("medio", "Por medio"),
        ("detalle", "Lectura de noticia"),
        ("copy_ia", "Copy con IA"),
        ("comunidad", "La comunidad"),
        ("imagenes", "Imágenes"),
    ]
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="visitas"
    )
    fecha = models.DateTimeField(default=timezone.now)
    seccion = models.CharField("sección", max_length=20, choices=SECCIONES)
    ruta = models.CharField(max_length=300)
    noticia = models.ForeignKey(
        "noticia.Noticia",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitas_clientes",
    )
    busqueda = models.CharField("búsqueda", max_length=200, blank=True)
    filtros = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    dispositivo = models.CharField(max_length=20, blank=True)
    navegador = models.CharField(max_length=60, blank=True)
    sesion = models.CharField(max_length=16, blank=True)

    class Meta:
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["usuario", "fecha"], name="visita_usuario_fecha_idx"),
            models.Index(fields=["fecha"], name="visita_fecha_idx"),
        ]

    def __str__(self):
        return f"{self.usuario} · {self.get_seccion_display()}"


class Acceso(models.Model):
    TIPOS = [
        ("login", "Ingreso"),
        ("logout", "Salida"),
        ("fallido", "Intento fallido"),
        ("bloqueado", "Acceso bloqueado"),
    ]
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accesos",
    )
    nombre_usuario = models.CharField("usuario ingresado", max_length=150, blank=True)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    fecha = models.DateTimeField(default=timezone.now)
    ip = models.GenericIPAddressField(null=True, blank=True)
    dispositivo = models.CharField(max_length=20, blank=True)
    navegador = models.CharField(max_length=60, blank=True)
    detalle = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["tipo", "fecha"], name="acceso_tipo_fecha_idx"),
            models.Index(fields=["usuario", "fecha"], name="acceso_usuario_fecha_idx"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.nombre_usuario}"
