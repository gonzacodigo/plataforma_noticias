import re
from urllib.parse import urlsplit
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from .managers import NoticiaManager


class Categoria(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["nombre"]

    def save(self, *args, **kwargs):
        self.nombre = self.nombre.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre.replace("ESPECTACULOS", "ESPECTÁCULOS").replace(
            "POLITICA", "POLÍTICA"
        )


class Noticia(models.Model):
    titulo = models.CharField(max_length=500)
    descripcion = models.TextField(blank=True)
    contenido = models.TextField(blank=True, default="")
    fecha = models.DateTimeField("Fecha de publicación")
    portada = models.URLField(max_length=2000, blank=True)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name="categoria_noticia"
    )
    medio = models.ForeignKey("medio.Medio", on_delete=models.PROTECT)
    visitas = models.PositiveBigIntegerField(default=0)
    url = models.URLField(max_length=2000, blank=True)
    fecha_ingesta = models.DateTimeField(default=timezone.now, editable=False)
    actualizado = models.DateTimeField(auto_now=True)
    fecha_estimada = models.BooleanField(default=False)
    solo_tendencias = models.BooleanField(
        default=False,
        help_text="Nota leída por RSS (solo título y bajada): alimenta las tendencias "
        "pero no aparece en el listado.",
    )
    objects = NoticiaManager()

    class Meta:
        ordering = ["-fecha", "-id"]
        indexes = [
            models.Index(fields=["-fecha", "-id"], name="noticia_fecha_idx"),
            models.Index(fields=["categoria", "-fecha"], name="noticia_categoria_idx"),
            models.Index(fields=["medio", "-fecha"], name="noticia_medio_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["medio", "url"],
                condition=~models.Q(url=""),
                name="noticia_medio_url_unique",
            )
        ]

    @property
    def texto_contenido(self):
        return re.sub(r"<br\s*/?>", "\n", self.contenido, flags=re.I)

    @property
    def source_url(self):
        try:
            parts = urlsplit(self.url)
            return (
                self.url
                if parts.scheme in ("http", "https")
                and parts.hostname
                and not parts.username
                else ""
            )
        except ValueError:
            return ""

    def get_absolute_url(self):
        return reverse("noticia_app:noticia_detail", args=[self.pk])

    def __str__(self):
        return self.titulo


class NoticiaImagen(models.Model):
    noticia = models.ForeignKey(
        Noticia, on_delete=models.CASCADE, related_name="imagenes"
    )
    url = models.URLField(max_length=2000)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["noticia", "url"], name="noticia_imagen_unique"
            )
        ]

    def __str__(self):
        return f"Imagen de: {self.noticia.titulo}"


class NoticiaAlias(models.Model):
    """Conserva los enlaces históricos tras unificar noticias repetidas."""

    original_id = models.PositiveBigIntegerField(unique=True)
    noticia = models.ForeignKey(
        Noticia, on_delete=models.PROTECT, related_name="aliases"
    )


TIPOS_IA = [
    ("resumen", "Resumen de la nota"),
    ("copy", "Copy para redes"),
    ("guion", "Guion para reel"),
    ("resumen_tendencia", "Resumen de la tendencia"),
]


class GeneracionIA(models.Model):
    """Un texto que generó la API de verdad.

    Se reparte a otros clientes que piden lo mismo, así cada nota paga una sola
    llamada por formato. La huella cambia si cambia el contenido de origen (por
    ejemplo, si a una tendencia se le suman notas) y obliga a generar de nuevo.
    """

    tipo = models.CharField(max_length=20, choices=TIPOS_IA)
    noticia = models.ForeignKey(
        Noticia, on_delete=models.CASCADE, null=True, blank=True, related_name="generaciones_ia"
    )
    tendencia = models.ForeignKey(
        "tendencias.Tendencia",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="generaciones_ia",
    )
    huella = models.CharField(max_length=64)
    texto = models.TextField()
    modelo = models.CharField(max_length=60)
    tokens_entrada = models.PositiveIntegerField(default=0)
    tokens_salida = models.PositiveIntegerField(default=0)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]
        verbose_name = "generación con IA"
        verbose_name_plural = "generaciones con IA"
        indexes = [
            models.Index(fields=["tipo", "noticia", "huella"], name="genia_noticia_idx"),
            models.Index(fields=["tipo", "tendencia", "huella"], name="genia_tendencia_idx"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} ({self.creado:%d/%m/%Y %H:%M})"


class CopyGenerado(models.Model):
    """Lo que recibió cada usuario: cuenta para su límite y guarda sus cambios."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="copys"
    )
    tipo = models.CharField(max_length=20, choices=TIPOS_IA, default="copy")
    noticia = models.ForeignKey(
        Noticia, on_delete=models.SET_NULL, null=True, related_name="copys"
    )
    tendencia = models.ForeignKey(
        "tendencias.Tendencia",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="copys",
    )
    generacion = models.ForeignKey(
        GeneracionIA, on_delete=models.SET_NULL, null=True, blank=True, related_name="entregas"
    )
    reutilizada = models.BooleanField(
        default=False, help_text="Se entregó una generación existente, sin llamar a la API."
    )
    texto = models.TextField(help_text="Versión del usuario, con sus cambios.")
    editado = models.DateTimeField(null=True, blank=True)
    modelo = models.CharField(max_length=60)
    tokens_entrada = models.PositiveIntegerField(default=0)
    tokens_salida = models.PositiveIntegerField(default=0)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]
        verbose_name = "generación entregada"
        verbose_name_plural = "generaciones entregadas"
        indexes = [
            models.Index(fields=["usuario", "creado"], name="copy_usuario_creado_idx")
        ]

    @classmethod
    def usados_este_mes(cls, usuario):
        inicio = timezone.localtime().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return cls.objects.filter(usuario=usuario, creado__gte=inicio).count()

    def __str__(self):
        return f"Copy de {self.usuario} ({self.creado:%d/%m/%Y})"


class ScrapeRun(models.Model):
    fuente = models.CharField(max_length=40)
    inicio = models.DateTimeField(auto_now_add=True)
    fin = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, default="running")
    detectadas = models.PositiveIntegerField(default=0)
    guardadas = models.PositiveIntegerField(default=0)
    existentes = models.PositiveIntegerField(default=0)
    omitidas = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-inicio"]
