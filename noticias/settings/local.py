from .base import *

DEBUG = True
SECRET_KEY = SECRET_KEY or "development-only-key-do-not-use-in-production-7f1a4dcb"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
DATABASES = database(default_sqlite=not bool(os.environ.get("DB_NAME")))
STORAGES["staticfiles"][
    "BACKEND"
] = "django.contrib.staticfiles.storage.StaticFilesStorage"
