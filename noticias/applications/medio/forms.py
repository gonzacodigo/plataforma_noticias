# forms.py
from django import forms
from applications.medio.models import Medio

class MedioForm(forms.Form):
    medio = forms.ModelChoiceField(
        queryset=Medio.objects.all(),
        required=False,
        empty_label="Todos los medios"
    )
