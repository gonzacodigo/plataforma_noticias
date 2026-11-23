"""Detección de tendencias: agrupa notas de distintos medios que cuentan lo mismo.

No depende de Django para poder probarse y ajustarse con datos sueltos: recibe
objetos con ``id``, ``titulo``, ``descripcion``, ``medio_id`` y ``fecha_ingesta``.
"""
import math
import re
import unicodedata
from collections import Counter

# Palabras que no identifican una historia: conectores, verbos de relleno de
# títulos periodísticos y términos que aparecen en casi cualquier nota.
VACIAS = set(
    """
    el la los las un una unos unas y o de del al a en con por para sin sobre tras desde entre hasta
    que como cuando donde quien cual cuales este esta estos estas ese esa eso esos esas aquel
    lo le les se su sus mi mis tu tus nos ya no si mas menos muy todo toda todos todas otro otra
    hoy ayer manana asi tambien pero aunque mientras luego despues antes ahora nunca siempre
    ser fue son era esta estan tiene tienen hizo hace habia hay sera seria
    dijo dice conto revelo mostro hablo confeso aseguro explico rompio compartio anuncio publico
    sorprendio respondio fulmino apunto lanzo mostro dejo quedo llego volvio paso sigue sumo
    tras sobre video videos foto fotos imagen imagenes exclusivo exclusiva mensaje mensajes
    redes sociales instagram tiktok twitter vivo aire programa nota noticia momento
    nuevo nueva nuevos nuevas gran grandes primer primera ultimo ultima mejor peor
    anos dias semana semanas horas meses lunes martes miercoles jueves viernes sabado domingo
    enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre
    argentina argentino argentinos buenos aires pais mundo vida cosas forma manera parte
    """.split()
)
PALABRA = re.compile(r"[a-zñ]{4,}")


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def claves(nota):
    """Palabras significativas del título y del comienzo de la bajada."""
    texto = f"{nota.titulo} {(nota.descripcion or '')[:140]}"
    palabras = PALABRA.findall(normalizar(texto))
    return {p for p in palabras if p not in VACIAS}


def agrupar(notas, umbral=0.22, minimo_compartidas=2):
    """Devuelve grupos (listas de notas) que cuentan la misma historia.

    Cada nota se compara con las notas ya agrupadas (no con la suma de sus
    palabras, para que un grupo no "absorba" historias vecinas). La similitud
    pondera cada palabra por lo rara que es en la ventana: un apellido pesa
    más que una palabra que aparece en muchas notas.
    """
    notas = sorted(notas, key=lambda n: (n.fecha_ingesta, n.id))
    conjuntos = {n.id: claves(n) for n in notas}
    frecuencia = Counter(p for c in conjuntos.values() for p in c)
    total = max(len(notas), 1)
    peso = {p: math.log(total / f) + 1 for p, f in frecuencia.items()}

    def similitud(a, b):
        comunes = a & b
        if len(comunes) < minimo_compartidas:
            return 0.0
        union = sum(peso[p] for p in a | b)
        return sum(peso[p] for p in comunes) / union if union else 0.0

    grupos = []
    grupo_de = {}
    for nota in notas:
        propias = conjuntos[nota.id]
        mejor, mejor_sim = None, 0.0
        for anterior in grupo_de:
            sim = similitud(propias, conjuntos[anterior])
            if sim > mejor_sim:
                mejor, mejor_sim = grupo_de[anterior], sim
        if mejor is not None and mejor_sim >= umbral:
            mejor.append(nota)
            grupo_de[nota.id] = mejor
        else:
            nuevo = [nota]
            grupos.append(nuevo)
            grupo_de[nota.id] = nuevo
    return grupos


def puntaje(cantidad_medios, cantidad_notas, horas_desde_ultima, lecturas=0, vida_media=12):
    """Más medios pesa más que más notas; lo reciente pesa más que lo viejo.

    La recencia se reduce a la mitad cada ``vida_media`` horas desde la última
    nota del grupo. Las lecturas de clientes suman un poco, con tope.
    """
    base = cantidad_medios * 10 + min(cantidad_notas, 10) + min(lecturas, 20) * 0.5
    return round(base * 0.5 ** (max(horas_desde_ultima, 0) / vida_media), 3)
