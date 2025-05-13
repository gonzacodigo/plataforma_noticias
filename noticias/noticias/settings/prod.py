# prod.py

from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False  # Cambiar a False en producción

ALLOWED_HOSTS = ['yourdomain.com']  # Agrega tus dominios permitidos

# Database
# Aquí agregas las configuraciones directamente en prod.py

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': "noticiasdb",  # Nombre de la base de datos
        'USER': "gonarc",  # Usuario de la base de datos
        'PASSWORD': "gonarccursopro",  # Contraseña de la base de datos
        'HOST': 'localhost',  # Host de la base de datos
        'PORT': '5432',  # Puerto de la base de datos
    }
}

# Static files (CSS, JavaScript, Images)
# Definir rutas de archivos estáticos

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR.child('static')]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR.child('media')

# Seguridad: reemplazar el `SECRET_KEY` directamente en prod.py
SECRET_KEY = "django-insecure-8vg5$b_$34_dww1!!&&kv-z#@c7ubqoul!##yj8wmw$+^l%zja"
