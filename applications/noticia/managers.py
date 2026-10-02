from datetime import datetime, time, timedelta
from django.db import models
from django.utils import timezone


class NoticiaManager(models.Manager):
    def buscar_noticia_titulo(self, kword):
        return self.filter(titulo__icontains=kword).order_by("-fecha", "-id")

    def buscar_noticia(self, fecha1=None, fecha2=None):
        queryset = self.filter(fecha__lte=timezone.now())
        if fecha1:
            day = (
                datetime.strptime(fecha1, "%Y-%m-%d").date()
                if isinstance(fecha1, str)
                else fecha1
            )
            queryset = queryset.filter(
                fecha__gte=timezone.make_aware(datetime.combine(day, time.min))
            )
        if fecha2:
            day = (
                datetime.strptime(fecha2, "%Y-%m-%d").date()
                if isinstance(fecha2, str)
                else fecha2
            )
            queryset = queryset.filter(
                fecha__lt=timezone.make_aware(
                    datetime.combine(day + timedelta(days=1), time.min)
                )
            )
        return queryset.order_by("-fecha", "-id")

    def listar_noticia_categoria(self, categoria_id):
        return self.filter(categoria_id=categoria_id).order_by("-fecha", "-id")

    def listar_noticia_medio(self, medio_id):
        return self.filter(medio_id=medio_id).order_by("-fecha", "-id")
