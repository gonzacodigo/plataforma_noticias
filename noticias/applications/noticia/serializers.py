from rest_framework import serializers
from .models import Noticia
from applications.medio.models import Medio
from applications.categoria.models import Categoria

class MedioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medio
        fields = ['id', 'nombre']  # ajustá los campos según tu modelo

class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ['id', 'nombre']  # igual, adaptalo según tu modelo

class NoticiaSerializer(serializers.ModelSerializer):
    medio = MedioSerializer(read_only=True)
    categoria = CategoriaSerializer(read_only=True)

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
