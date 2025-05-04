from django.db import models
from applications.medio.models import Medio
from .managers import NoticiaManager



# Create your models here.
class Categoria(models.Model):
    nombre = models.CharField(max_length=50)

    def __str__(self):
        return self.nombre.upper()

class Noticia(models.Model):
    titulo = models.CharField(max_length=500)
    descripcion = models.TextField()
    contenido = models.TextField(default="Texto por defecto")
    fecha = models.DateTimeField(("Fecha"), auto_now=False, auto_now_add=False)
    portada = models.URLField(max_length=500, blank=True)
    categoria = models.ForeignKey(Categoria, 
                                on_delete=models.CASCADE,
                                related_name= 'categoria_noticia'
                                )
    medio = models.ForeignKey(Medio, on_delete=models.CASCADE)
    visitas = models.PositiveBigIntegerField(default=0)
    url = models.URLField(max_length=500, blank=True)
    objects = NoticiaManager()

    def __str__(self):
        return self.titulo
