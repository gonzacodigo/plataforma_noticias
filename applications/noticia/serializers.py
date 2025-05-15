from rest_framework import serializers
from applications.noticia.models import Noticia


class NoticiaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Noticia
        fields = [
            'id',
            'titulo',
            'descripcion',
            'fecha',
            'portada',
            'url',
            'categoria',
            'medio',
            'visitas',
        ]
