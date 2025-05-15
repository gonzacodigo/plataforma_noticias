from datetime import datetime, timedelta
from django.db import models
from django.utils.timezone import now

class NoticiaManager(models.Manager):
    def buscar_noticia_titulo(self, kword):
        return self.filter(titulo__icontains=kword).order_by('-fecha')

    def buscar_noticia(self, fecha1=None, fecha2=None):
        if not fecha1 and not fecha2:
            return self.filter(fecha__lte=now()).order_by('-fecha')

        date1 = datetime.strptime(fecha1, "%Y-%m-%d")
        date2 = datetime.strptime(fecha2, "%Y-%m-%d") + timedelta(days=1)

        return self.filter(fecha__gte=date1, fecha__lt=date2).order_by('fecha')
    
    def listar_noticia_categoria(self, categoria_id):
        return self.filter(categoria__id=categoria_id).order_by('-fecha')
    
    def listar_noticia_medio(self, medio_id):
        return self.filter(medio__id=medio_id).order_by('-fecha')


    


