# Desenchufadas · Plataforma de noticias

Aplicación Django para consultar noticias de Infobae, TN, Telefe y Clarín, y de los medios de espectáculos Ciudad Magazine, Primicias Ya, Pronto y La Nación Espectáculos. La ingesta funciona independientemente de las visitas. El sitio usa CSS propio y JavaScript mínimo, sin Foundation, jQuery o fuentes externas.

## Desarrollo

Python 3.13 y Django 5.2 LTS. Crear un entorno virtual `.venv` e instalar `pip install -r requirements.lock.txt`. Copiar `.env.example` a `.env` y completar los valores. Para una demostración local sin PostgreSQL, definir `USE_SQLITE=true`.

Ejecutar `python manage.py migrate`, `python manage.py createsuperuser` y `python manage.py runserver`. Las pruebas se ejecutan con `python manage.py test --settings=noticias.settings.test`; no utilizan la base real.

## Actualización

`python manage.py actualizar_noticias --settings=noticias.settings.prod` actualiza todas las fuentes. `--fuente tn` limita una fuente; `--force` ignora el resultado reciente. Los medios se procesan en paralelo (`--paralelo`, 4 por defecto con PostgreSQL y 1 con SQLite, que no admite escrituras simultáneas); las fuentes de un mismo medio van en orden. Las notas ya guardadas no se vuelven a descargar, por lo que una pasada habitual tarda segundos. Las fuentes que publican otros temas se limitan a sus secciones de espectáculos (`SECTIONS` en `services/engine.py`). Las galerías o videos sin texto se omiten sin marcar la ejecución como parcial, salvo que sean mayoría, lo que indica selectores rotos. Programar el comando cada 10–15 minutos en el sistema de tareas del servidor. Mantener la ejecución fuera de los workers HTTP.

Se limitan artículos, tamaño de respuesta, timeout y duración. Hay bloqueo entre procesos por medio, resultados recientes compartidos en disco y registro de cada ejecución en el administrador. El bloqueo es por host; para varios servidores, usar una cola y un bloqueo distribuidos antes de escalar. Los fallos devuelven código de salida no cero para alertas.

Las rutas históricas `/api/noticias/.../` admiten únicamente POST de administradores autenticados mediante sesión, con CSRF y cuota de seis solicitudes por hora. No se usan desde la página pública. Si una actualización dura demasiado para el proxy, usar el comando programado.

## Copys con IA

Los usuarios con cuenta pueden generar, desde el detalle de cada noticia, un copy para Instagram con la API de Claude. Las cuentas se crean desde el administrador; el acceso es en `/ingresar/`. Definir `ANTHROPIC_API_KEY` en `.env` (sin clave, la función no se muestra), `COPY_IA_MODELO` (por defecto `claude-opus-5-5`) y `COPY_IA_LIMITE_MENSUAL` (copys por usuario y mes, por defecto 100). Cada copy queda registrado con sus tokens en el administrador, en "Copy generados". Usar una clave distinta por entorno y un límite de gasto en la Console de Anthropic. Las pruebas simulan la API y no consumen crédito.

## Clientes, acceso y actividad

El listado de noticias es público (inicio, búsqueda, categorías, medios y "La comunidad"): funciona como vidriera para buscadores y redes. Leer cada noticia, el copy con IA y el buscador de imágenes exigen ingresar en `/ingresar/`, que vuelve a la noticia pedida. La lista de vistas públicas está en `applications/cuentas/middleware.py` (`VISTAS_PUBLICAS`). Cada usuario que no es staff debe pertenecer a un **Cliente** (Administración › Clientes), que define plan, precio mensual, vencimiento, máximo de usuarios, límite de copys con IA y "sesión única" (una sesión abierta por usuario). Si un cliente vence o se suspende, sus usuarios pierden el acceso en el siguiente clic. Tras 5 contraseñas erróneas, ese usuario queda bloqueado 15 minutos desde esa IP.

Se registran los ingresos, las salidas, los intentos fallidos y cada sección que visita un cliente: búsquedas, filtros, noticia leída, dispositivo, navegador e IP. El staff no se registra (`ACTIVIDAD_REGISTRAR_STAFF=true` lo activa). El **Panel de uso** (`/admin/panel/`, enlazado al inicio del administrador) muestra la actividad por día y por hora, las secciones, los medios, las búsquedas, las noticias más leídas y una tabla por usuario con alertas de vencimientos, inactividad y posibles cuentas compartidas. En producción la IP se toma de `X-Real-IP` (nginx). `python manage.py limpiar_actividad` borra la actividad de más de 365 días (`--dias` o `ACTIVIDAD_RETENCION_DIAS`). Informá a los clientes en el contrato que se registra su uso.

## Medios por RSS

La Nación (general), Perfil, Página/12, C5N y Ámbito se descubren por RSS o sitemap de noticias (`applications/noticia/services/feeds.py`, `FEEDS`): el canal da título, fecha, foto y enlace de cada nota nueva, y luego se baja su página para extraer el texto completo (JSON-LD, el contenido de Arc o párrafos, en ese orden). Las notas marcadas por el medio como exclusivas para suscriptores (`isAccessibleForFree: false`), o cuyo texto no se puede leer, se guardan solo como resumen (`solo_tendencias`): alimentan las tendencias, no aparecen en el listado ni en el buscador, y su tarjeta lleva al medio original. La categoría sale de la URL, de la sección del medio o del RSS. Se aceptan subdominios del medio (Perfil reenvía a Caras o Exitoína). Las notas de espectáculos de La Nación siguen viniendo del adaptador `lanacion_show`. Cada canal es una entrada de configuración, y `FEED_MAX_ITEMS` limita las notas por pasada.

## Tendencias

Al final de cada `actualizar_noticias` (y con `python manage.py calcular_tendencias`) se agrupan las notas de las últimas 36 horas que cuentan la misma historia en distintos medios (`applications/tendencias/motor.py`: títulos y comienzo de la bajada, palabras ponderadas por rareza). Un grupo es tendencia si lo publicaron al menos 3 medios distintos en Espectáculos, o 4 en el resto de las categorías (`TENDENCIAS_MIN_MEDIOS_GENERAL`). Su puntaje suma los medios (lo principal), las notas y las lecturas de clientes, y se reduce a la mitad cada 12 horas. Su título es el de la nota que un medio publicó primero. Una falla en este cálculo no detiene la ingesta. La portada, sin filtros, muestra públicamente dos apartados: el top 3 de Espectáculos y el top 3 de General (todas las demás categorías juntas), y `/tendencia/<id>/` muestra solo a clientes cómo contó cada medio la historia. Desde Administración › Tendencias se puede ocultar una tendencia mal agrupada. Ajustes: `TENDENCIAS_VENTANA_HORAS`, `TENDENCIAS_MIN_MEDIOS`, `TENDENCIAS_UMBRAL` y `TENDENCIAS_POR_CATEGORIA`.

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
