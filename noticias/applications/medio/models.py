from django.db import models

# Create your models here.

class Medio(models.Model):
    nombre = models.CharField(
        max_length=50
    )
    categoria = models.CharField(
        max_length=50
    )
    def __str__(self):
        return str(self.nombre) 