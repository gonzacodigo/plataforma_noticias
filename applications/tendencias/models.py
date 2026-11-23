from django.db import models
from django.urls import reverse
from django.utils import timezone


class Tendencia(models.Model):
    """Una historia que cuentan varios medios a la vez."""

    categoria = models.ForeignKey(
        "noticia.Categoria", on_delete=models.PROTECT, related_name="tendencias"
    )
    titulo = models.CharField(
        "título", max_length=500, help_text="Título de la nota que un medio publicó primero sobre el tema."
    )
    nota_principal = models.ForeignKey(
        "noticia.Noticia",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="primera nota",
    )
    noticias = models.ManyToManyField("noticia.Noticia", related_name="tendencias")
    medios = models.JSONField(default=list, blank=True)
    cantidad_medios = models.PositiveSmallIntegerField("medios", default=0)
    cantidad_notas = models.PositiveSmallIntegerField("notas", default=0)
    lecturas = models.PositiveIntegerField(
        default=0, help_text="Lecturas de clientes de las notas del tema en la ventana."
    )
    puntaje = models.FloatField(default=0)
    primera_aparicion = models.DateTimeField("primera aparición")
    ultima_aparicion = models.DateTimeField("última aparición")
    activa = models.BooleanField(
        default=True, help_text="Se desactiva sola cuando el tema deja de estar en la ventana."
    )
    oculta = models.BooleanField(
        default=False,
        help_text="Marcala para que no se muestre (por ejemplo, si agrupó mal dos historias).",
    )
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-puntaje"]
        indexes = [
            models.Index(fields=["activa", "oculta", "-puntaje"], name="tendencia_activa_idx")
        ]

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        return reverse("tendencias:detalle", args=[self.pk])

    @property
    def hace(self):
        """Antigüedad corta desde que apareció el tema: "hace 3 h"."""
        minutos = max(int((timezone.now() - self.primera_aparicion).total_seconds() // 60), 0)
        if minutos < 60:
            return f"hace {max(minutos, 1)} min"
        if minutos < 60 * 24:
            return f"hace {minutos // 60} h"
        dias = minutos // (60 * 24)
        return f"hace {dias} día{'s' if dias > 1 else ''}"
