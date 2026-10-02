import re
from urllib.parse import urlsplit
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


class ScrapeRun(models.Model):
    fuente = models.CharField(max_length=40)
    inicio = models.DateTimeField(auto_now_add=True)
    fin = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, default="running")
    detectadas = models.PositiveIntegerField(default=0)
    guardadas = models.PositiveIntegerField(default=0)
    omitidas = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-inicio"]
