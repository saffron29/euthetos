"""
Lectura del currículo (CV): saca el texto del archivo y propone un perfil.

El CV se procesa en memoria y no se guarda en ningún lado. Lo que aquí se
propone (grado y periodos de trabajo) es una ESTIMACIÓN hecha con reglas:
la aplicación muestra cada periodo leído y la persona decide cuáles cuentan.
"""

import io
import math
import re
import zipfile
from datetime import date

from reglas import BACHILLER, EGRESADO, ESTUDIANTE, MAESTRIA, TECNICO, TITULO, normalizar


# ---------------------------------------------------------------------------
# 1. Del archivo al texto
# ---------------------------------------------------------------------------
def leer_cv(nombre, contenido):
    """Devuelve el texto de un CV en PDF, Word (.docx) o texto plano."""
    nombre = nombre.lower()
    if nombre.endswith(".pdf"):
        from pypdf import PdfReader
        lector = PdfReader(io.BytesIO(contenido))
        return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
    if nombre.endswith(".docx"):
        # Un .docx es un zip; el texto está en word/document.xml, un párrafo por <w:p>
        with zipfile.ZipFile(io.BytesIO(contenido)) as archivo:
            xml = archivo.read("word/document.xml").decode("utf-8")
        parrafos = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
        return "\n".join("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in parrafos)
    return contenido.decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# 2. Grado más alto que menciona el CV
# ---------------------------------------------------------------------------
PISTAS_DE_GRADO = [
    (MAESTRIA, r"magister en|maestr[oa] en|grado de maestr|master en|\bmba\b"),
    (TITULO, r"licenciad[oa]|titulo profesional|titulad[oa]|abogad[oa]|ingenier[oa] (civil|industrial|de sistemas)"
             r"|contador publico|medico cirujano"),
    (BACHILLER, r"bachiller"),
    (EGRESADO, r"egresad[oa]"),
    (ESTUDIANTE, r"estudiante de|\b\d{1,2}(vo|mo|no|to|er|do)? ciclo"),
    (TECNICO, r"tecnic[oa] en|profesional tecnic"),
]


def grado_del_cv(texto):
    """El grado más alto que aparece escrito en el CV (o None si no se reconoce)."""
    texto = normalizar(texto)
    for nivel, patron in PISTAS_DE_GRADO:
        if re.search(patron, texto):
            return nivel
    return None


# ---------------------------------------------------------------------------
# 3. Periodos de trabajo: se leen de la sección "Experiencia"
# ---------------------------------------------------------------------------
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
         "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
NOMBRE_DE_MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
_NOMBRE = r"(ene|feb|mar|abr|may|jun|jul|ago|set|sep|oct|nov|dic)[a-z]*\.?,?\s*(?:de\s+|del\s+)?"
_MES = r"(?:" + _NOMBRE + r"|(\d{1,2})\s*[/.]\s*)?"
_FECHA = _MES + r"((?:19|20)\d{2})"
_HOY = r"actualidad|presente|a la fecha|hoy|actual|vigente|current|present"
# "marzo 2021 – agosto 2023", "03/2021 - 08/2023", "2021 - 2023", "enero 2023 – actualidad"
PATRON_PERIODO = re.compile(_FECHA + r"\s*(?:-|–|—|\ba\b|\bal\b|\bhasta\b)\s*(?:la\s+)?(?:" + _FECHA + "|(" + _HOY + "))")
# "junio 2026" suelto: un trabajo de un solo mes
PATRON_UN_MES = re.compile(r"\b" + _NOMBRE + r"((?:19|20)\d{2})")

TITULO_EXPERIENCIA = r"^(experiencia|trayectoria|historial laboral|practicas)"
OTROS_TITULOS = (r"^(formacion|educacion|estudios|cursos|capacitacion|idiomas|habilidades|competencias|"
                 r"referencias|conocimientos|publicaciones|voluntariado|datos personales|certificaciones|"
                 r"logros|informacion adicional|otros datos|investigacion|perfil)")
VINETAS = ("•", "-", "*", "·", "▪", "–", "o ")


def seccion_experiencia(texto):
    """Las líneas del CV que están bajo un título como "Experiencia laboral"."""
    lineas, dentro = [], False
    for linea in texto.splitlines():
        limpia = normalizar(linea)
        if len(limpia) < 50 and re.search(TITULO_EXPERIENCIA, limpia):
            dentro = True
        elif len(limpia) < 50 and re.search(OTROS_TITULOS, limpia):
            dentro = False
        elif dentro and limpia:
            lineas.append(linea.strip())
    return lineas


def _mes(nombre, numero, por_defecto):
    if nombre:
        return MESES[nombre]
    if numero and 1 <= int(numero) <= 12:
        return int(numero)
    return por_defecto


def _en_palabras(inicio, fin):
    """(24253, 24260) -> 'feb 2021 – ago 2021'. Los meses se cuentan desde el año 0."""
    def fecha(meses):
        return f"{NOMBRE_DE_MES[meses % 12]} {meses // 12}"
    return fecha(inicio) if fin - inicio == 1 else f"{fecha(inicio)} – {fecha(fin - 1)}"


def periodos_de_trabajo(texto, hoy=None):
    """Lista de periodos leídos de la sección "Experiencia" del CV.

    Cada periodo es un diccionario con el inicio y el fin contados en meses,
    su duración y la línea del CV de donde salió, para que la persona lo reconozca.
    """
    hoy = hoy or date.today()
    ahora = hoy.year * 12 + hoy.month
    lineas, periodos = seccion_experiencia(texto), []

    for numero, linea in enumerate(lineas):
        limpia, encontrados = normalizar(linea), []
        for m in PATRON_PERIODO.finditer(limpia):
            mes1, num1, anio1, mes2, num2, anio2, sigue = m.groups()
            inicio = int(anio1) * 12 + _mes(mes1, num1, 1) - 1
            if sigue:
                fin = ahora
            elif mes2 or num2:
                fin = int(anio2) * 12 + _mes(mes2, num2, 12)
            elif mes1 or num1:
                fin = int(anio2) * 12 + 12
            else:                               # "2021 – 2023": solo años, se cuentan 2
                fin = int(anio2) * 12 if anio2 != anio1 else inicio + 6
            encontrados.append((inicio, fin))

        # Un mes suelto solo vale en la línea que encabeza un trabajo, no dentro de una viñeta
        es_encabezado = not linea.startswith(VINETAS) and ("|" in linea or len(linea) < 70)
        if not encontrados and es_encabezado:
            for m in PATRON_UN_MES.finditer(limpia):
                inicio = int(m.group(2)) * 12 + MESES[m.group(1)] - 1
                encontrados.append((inicio, inicio + 1))

        for inicio, fin in encontrados:
            if not inicio < fin <= ahora + 1:
                continue                        # fechas futuras o al revés
            # Si la línea solo trae la fecha, el nombre del trabajo está en la línea anterior
            detalle = linea
            if len(PATRON_PERIODO.sub("", limpia).strip(" |-·,")) < 25 and numero > 0:
                detalle = f"{lineas[numero - 1]} · {linea}"
            periodos.append({"inicio": inicio, "fin": fin, "meses": fin - inicio,
                             "periodo": _en_palabras(inicio, fin), "detalle": detalle[:140]})
    return periodos


def sumar_periodos(periodos):
    """Años trabajados, sin contar dos veces los periodos que se superponen."""
    tramos = sorted((p["inicio"], p["fin"]) for p in periodos)
    if not tramos:
        return 0.0
    meses, (inicio, fin) = 0, tramos[0]
    for otro_inicio, otro_fin in tramos[1:]:
        if otro_inicio <= fin:                  # se superponen: se unen
            fin = max(fin, otro_fin)
        else:
            meses += fin - inicio
            inicio, fin = otro_inicio, otro_fin
    meses += fin - inicio
    return math.floor(meses / 12 * 2) / 2       # hacia abajo, de medio año en medio año


def estimar_perfil(texto, hoy=None):
    """Lo que Euthetos propone a partir del CV; la persona lo confirma en pantalla."""
    periodos = periodos_de_trabajo(texto, hoy)
    return {
        "nivel": grado_del_cv(texto),
        "colegiado": bool(re.search(r"colegiad|colegiatura|n° de colegio|cap n|cip n|cal n", normalizar(texto))),
        "periodos": periodos,
        "anios_experiencia": sumar_periodos(periodos) if periodos else None,
    }
