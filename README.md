# Desenchufadas · Plataforma de noticias

Aplicación Django para consultar noticias de Infobae, TN, Telefe y Clarín. La ingesta funciona independientemente de las visitas. El sitio usa CSS propio y JavaScript mínimo, sin Foundation, jQuery o fuentes externas.

## Desarrollo

Python 3.13 y Django 5.2 LTS. Crear un entorno virtual `.venv` e instalar `pip install -r requirements.lock.txt`. Copiar `.env.example` a `.env` y completar los valores. Para una demostración local sin PostgreSQL, definir `USE_SQLITE=true`.

Ejecutar `python manage.py migrate`, `python manage.py createsuperuser` y `python manage.py runserver`. Las pruebas se ejecutan con `python manage.py test --settings=noticias.settings.test`; no utilizan la base real.

## Actualización

`python manage.py actualizar_noticias --settings=noticias.settings.prod` actualiza todas las fuentes. `--fuente tn` limita una fuente; `--force` ignora el resultado reciente. Programar el comando cada 10–15 minutos en el sistema de tareas del servidor. Mantener la ejecución fuera de los workers HTTP.

Se limitan artículos, tamaño de respuesta, timeout y duración. Hay bloqueo entre procesos por medio, resultados recientes compartidos en disco y registro de cada ejecución en el administrador. El bloqueo es por host; para varios servidores, usar una cola y un bloqueo distribuidos antes de escalar. Los fallos devuelven código de salida no cero para alertas.

Las rutas históricas `/api/noticias/.../` admiten únicamente POST de administradores autenticados mediante sesión, con CSRF y cuota de seis solicitudes por hora. No se usan desde la página pública. Si una actualización dura demasiado para el proxy, usar el comando programado.

## Producción

Configurar `DJANGO_SETTINGS_MODULE=noticias.settings.prod`, una clave aleatoria de al menos 50 caracteres y credenciales PostgreSQL. No usar `secret.json`; está excluido de Git. WSGI y ASGI seleccionan producción explícitamente. Ejecutar `python manage.py check --deploy --settings=noticias.settings.prod` y `python manage.py collectstatic --noinput --settings=noticias.settings.prod`.

Servir `staticfiles/` con el servidor web; Gunicorn/Uvicorn y el proxy se configuran en el servidor. Configurar HTTPS antes de activar el sitio. Solo activar `TRUST_PROXY_HTTPS` si el proxy es confiable y reemplaza cabeceras de cliente. La redirección HTTPS y cookies seguras están activadas en producción. HSTS comienza con una hora y sin incluir subdominios.

## Migraciones y respaldo

Antes de migrar una base existente, generar un respaldo completo con `pg_dump`, validar una restauración en una base de ensayo y ejecutar allí las migraciones. Las migraciones de integridad se detienen si encuentran medios normalizados, artículos o imágenes duplicados: no eliminan datos automáticamente. El comando `revisar_duplicados` muestra los grupos y permite preparar una limpieza revisable sin perder registros. Conservar el respaldo y la versión anterior hasta validar el sitio.

Para rollback, restaurar código y base desde la copia comprobada: los modelos nuevos no son compatibles con una base sin migrar. Mantener al menos una copia fuera del servidor y probar restauraciones periódicamente.

## Seguridad y datos

Rotar las credenciales históricamente versionadas y revisar quién accedió al repositorio. Retirar `secret.json` del índice actual no borra versiones anteriores; sanear el historial requiere coordinación con todos los clones. La clave nueva invalida sesiones firmadas anteriores. La contraseña PostgreSQL debe cambiarse también en el servidor antes de actualizar `.env`.

Los artículos se guardan como texto y se muestran escapados. La ingesta valida dominios/redirecciones y direcciones públicas. Las imágenes mantienen su origen externo y pueden dejar de estar disponibles. Las fechas estimadas se distinguen de fechas de publicación reales. La categoría y el medio están protegidos contra eliminaciones en cascada.

Los selectores de terceros pueden cambiar: mantener fixtures de cada medio y consultar las ejecuciones fallidas. Revisar autorización de reutilización de contenido según el uso editorial del proyecto. El diseño se basa en la marca y mascota ya incluidas; el acceso automático al perfil Instagram no estuvo disponible durante esta revisión.

## Arranque en esta computadora

Se preparó un entorno `.venv` actualizado. Abrir `iniciar.cmd` inicia el sitio en http://127.0.0.1:8000; `actualizar.cmd` recolecta noticias manualmente. La configuración local usa SQLite porque PostgreSQL no estaba disponible durante la actualización. Las credenciales anteriores se conservan en `.env`; para volver a PostgreSQL, respaldar y migrar primero la base y definir `USE_SQLITE=false`. No hay transferencia automática del historial PostgreSQL a SQLite.

`/salud/` devuelve 200 cuando la base responde y 503 si no está disponible. No expone credenciales ni excepciones.
