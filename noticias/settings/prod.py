from django.core.exceptions import ImproperlyConfigured
from .base import *

DEBUG = False
if (
    len(SECRET_KEY) < 50
    or SECRET_KEY.startswith(("django-insecure-", "development-", "REEMPLAZAR"))
    or len(set(SECRET_KEY)) < 5
):
    raise ImproperlyConfigured(
        "Producción requiere DJANGO_SECRET_KEY aleatoria de al menos 50 caracteres."
    )
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get(
        "ALLOWED_HOSTS", "www.desenchufadas.com,desenchufadas.com"
    ).split(",")
    if h.strip()
]
CSRF_TRUSTED_ORIGINS = [
    h.strip()
    for h in os.environ.get(
        "CSRF_TRUSTED_ORIGINS",
        "https://www.desenchufadas.com,https://desenchufadas.com",
    ).split(",")
    if h.strip()
]
if boolean("USE_SQLITE"):
    raise ImproperlyConfigured(
        "Producción requiere PostgreSQL. Define USE_SQLITE=false en el entorno del servidor."
    )
DATABASES = database()
SECURE_SSL_REDIRECT = boolean("SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
if boolean("TRUST_PROXY_HTTPS"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
