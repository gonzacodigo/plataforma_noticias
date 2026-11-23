from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver
from .models import Perfil
from .utils import huella_sesion, registrar_acceso


@receiver(user_logged_in)
def al_ingresar(sender, request, user, **kwargs):
    if request is None:
        return
    registrar_acceso(request, "login", user)
    # La sesión nueva pasa a ser la única válida si el cliente lo exige.
    Perfil.objects.filter(usuario=user).update(
        sesion_actual=huella_sesion(request.session.session_key)
    )


@receiver(user_logged_out)
def al_salir(sender, request, user, **kwargs):
    if request is None or user is None or getattr(request, "_sin_registro_salida", False):
        return
    registrar_acceso(request, "logout", user)


@receiver(user_login_failed)
def al_fallar(sender, credentials, request=None, **kwargs):
    if request is None:
        return
    registrar_acceso(request, "fallido", nombre=credentials.get("username", ""))
