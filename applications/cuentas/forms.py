from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from .utils import client_ip, motivo_bloqueo

INTENTOS_MAXIMOS = 5
BLOQUEO_SEGUNDOS = 15 * 60


class IngresoForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Usuario o contraseña incorrectos.",
        "inactive": "Tu usuario está desactivado.",
    }

    def _clave_intentos(self):
        usuario = (self.data.get("username") or "").strip().lower()[:150]
        return f"ingreso-fallido:{client_ip(self.request)}:{usuario}"

    def clean(self):
        clave = self._clave_intentos()
        if cache.get(clave, 0) >= INTENTOS_MAXIMOS:
            raise ValidationError(
                "Demasiados intentos fallidos. Esperá 15 minutos y probá de nuevo.",
                code="bloqueado",
            )
        try:
            return super().clean()
        except ValidationError:
            if self.user_cache is None:
                cache.set(clave, cache.get(clave, 0) + 1, BLOQUEO_SEGUNDOS)
            raise

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        motivo = motivo_bloqueo(user)
        if motivo:
            raise ValidationError(motivo, code="sin_acceso")
