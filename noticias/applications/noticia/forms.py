# applications/noticia/forms.py

from django import forms
from .models import Categoria

class CategoriaForm(forms.Form):
    categorias = forms.ModelMultipleChoiceField(
        queryset=Categoria.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )