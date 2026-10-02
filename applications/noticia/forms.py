from django import forms
from datetime import date
from .models import Categoria
from applications.medio.models import Medio


class BusquedaForm(forms.Form):
    kword = forms.CharField(
        label="Buscar noticias",
        required=False,
        max_length=150,
        widget=forms.TextInput(
            attrs={"placeholder": "¿Qué está pasando?", "type": "search"}
        ),
    )
    categoria = forms.ModelChoiceField(
        label="Categoría",
        queryset=Categoria.objects.all(),
        required=False,
        empty_label="Todas las categorías",
    )
    medio = forms.ModelChoiceField(
        label="Medio",
        queryset=Medio.objects.all(),
        required=False,
        empty_label="Todos los medios",
    )
    fecha1 = forms.DateField(
        label="Desde", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    fecha2 = forms.DateField(
        label="Hasta", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    categorias = forms.ModelMultipleChoiceField(
        queryset=Categoria.objects.all(),
        required=False,
        widget=forms.MultipleHiddenInput,
    )

    def clean(self):
        data = super().clean()
        if (
            data.get("fecha1")
            and data.get("fecha2")
            and data["fecha1"] > data["fecha2"]
        ):
            self.add_error(
                "fecha2", "La fecha final debe ser posterior o igual a la inicial."
            )
        if data.get("fecha2") == date.max:
            self.add_error(
                "fecha2", "Elegí una fecha anterior al último día del año 9999."
            )
        return data


class CategoriaForm(forms.Form):
    categorias = forms.ModelMultipleChoiceField(
        queryset=Categoria.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
