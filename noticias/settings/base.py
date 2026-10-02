import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = json.loads(value)
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)


def boolean(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("true", "1", "yes")


def database(default_sqlite=False):
    if boolean("USE_SQLITE", default_sqlite):
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": os.environ.get("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
            }
        }
    from django.core.exceptions import ImproperlyConfigured

    if any(not os.environ.get(k) for k in ("DB_NAME", "DB_USER", "DB_PASSWORD")):
        raise ImproperlyConfigured(
            "Configura DB_NAME, DB_USER y DB_PASSWORD en .env o en el entorno."
        )
    return {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ["DB_USER"],
            "PASSWORD": os.environ["DB_PASSWORD"],
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {"connect_timeout": 10},
        }
    }


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "applications.medio",
    "applications.noticia",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "noticias.middleware.SecurityHeadersMiddleware",
]
ROOT_URLCONF = "noticias.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "applications.noticia.context_processors.brand",
            ]
        },
    }
]
WSGI_APPLICATION = "noticias.wsgi.application"
ASGI_APPLICATION = "noticias.asgi.application"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation." + n}
    for n in [
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    ]
]
LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
    },
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
SITE_URL = os.environ.get("SITE_URL", "https://www.desenchufadas.com").rstrip("/")
INSTAGRAM_URL = "https://www.instagram.com/desenchufadas.ok/"
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAdminUser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication"
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_RATES": {"scrape": "6/hour"},
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(BASE_DIR / ".cache" / "django"),
        "TIMEOUT": 300,
    }
}
SCRAPE_MAX_ARTICLES = int(os.environ.get("SCRAPE_MAX_ARTICLES", "30"))
SCRAPE_BUDGET_SECONDS = int(os.environ.get("SCRAPE_BUDGET_SECONDS", "90"))
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"}
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
