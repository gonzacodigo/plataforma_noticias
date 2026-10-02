from django.db import models


class Medio(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    categoria = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        ordering = ["nombre"]

    def save(self, *args, **kwargs):
        self.nombre = self.nombre.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre
