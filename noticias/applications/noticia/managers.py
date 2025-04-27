from datetime import datetime
from django.db import models

class LibroManager(models.Manager):
    def buscar_libro(self, kword):
        return self.filter(titulo__icontains=kword)

    def buscar_libro_2(self, fecha1, fecha2):
        date1 = datetime.strptime(fecha1, "%Y-%m-%d").date()
        date2 = datetime.strptime(fecha2, "%Y-%m-%d").date()


        return self.filter(fecha__range=(date1, date2))
    
    def listar_libro_categoria(self, categoria):
        return self.filter(categoria__id = categoria).order_by('titulo')
    
    def add_autor_libro(self, libro_id, autor):
        libro = self.get(id = libro_id)
        libro.autores.add(autor)
        return libro



class CategoriaManager(models.Manager):
    #se llama a esta funcion
    def categoria_autor(self, autor):
        return self.filter(
            categoria_libro__autores__id = autor
        ).distinct()



