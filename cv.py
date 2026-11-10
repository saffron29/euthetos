"""
Lectura del currículo (CV): saca el texto del archivo y propone un perfil.

El CV se procesa en memoria y no se guarda en ningún lado. Lo que aquí se
propone (grado y años de experiencia) es una ESTIMACIÓN hecha con reglas:
la persona siempre la revisa y la corrige en la pantalla antes de buscar.
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
# 3. Años de experiencia: se suman los periodos de la sección «Experiencia»
# ---------------------------------------------------------------------------
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
         "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
_MES = r"(?:(ene|feb|mar|abr|may|jun|jul|ago|set|sep|oct|nov|dic)[a-z]*\.?,?\s*(?:de\s+|del\s+)?|(\d{1,2})\s*[/.]\s*)?"
_FECHA = _MES + r"((?:19|20)\d{2})"
_HOY = r"actualidad|presente|a la fecha|hoy|actual|vigente|current|present"
PATRON_PERIODO = re.compile(_FECHA + r"\s*(?:-|–|—|\ba\b|\bal\b|\bhasta\b)\s*(?:la\s+)?(?:" + _FECHA + "|(" + _HOY + "))")

TITULO_EXPERIENCIA = r"^(experiencia|trayectoria|historial laboral|practicas)"
OTROS_TITULOS = (r"^(formacion|educacion|estudios|cursos|capacitacion|idiomas|habilidades|competencias|"
                 r"referencias|conocimientos|publicaciones|voluntariado|datos personales|certificaciones|"
                 r"logros|informacion adicional|otros datos)")


def seccion_experiencia(texto):
    """Las líneas del CV que están bajo un título como «Experiencia laboral»."""
    lineas, dentro = [], False
    for linea in texto.splitlines():
        limpia = normalizar(linea)
        if len(limpia) < 50 and re.search(TITULO_EXPERIENCIA, limpia):
            dentro = True
        elif len(limpia) < 50 and re.search(OTROS_TITULOS, limpia):
            dentro = False
        elif dentro:
            lineas.append(limpia)
    return "\n".join(lineas)


def _mes(nombre, numero, por_defecto):
    if nombre:
        return MESES[nombre]
    if numero and 1 <= int(numero) <= 12:
        return int(numero)
    return por_defecto


def periodos_de_trabajo(texto, hoy=None):
    """Lista de (inicio, fin) contados en meses, uno por cada «mar 2021 – ago 2023» del texto."""
    hoy = hoy or date.today()
    periodos = []
    for m in PATRON_PERIODO.finditer(texto):
        mes1, num1, anio1, mes2, num2, anio2, sigue = m.groups()
        inicio = int(anio1) * 12 + _mes(mes1, num1, 1) - 1
        if sigue:
            fin = hoy.year * 12 + hoy.month
        elif mes2 or num2:
            fin = int(anio2) * 12 + _mes(mes2, num2, 12)
        elif mes1 or num1:
            fin = int(anio2) * 12 + 12
        else:                                   # «2021 – 2023»: solo años, se cuentan 2
            fin = int(anio2) * 12 if anio2 != anio1 else inicio + 6
        if inicio < fin <= hoy.year * 12 + hoy.month + 1:
            periodos.append((inicio, fin))
    return periodos


def anios_de_experiencia(texto, hoy=None):
    """Suma los periodos de trabajo sin contar dos veces los que se superponen."""
    periodos = sorted(periodos_de_trabajo(seccion_experiencia(texto), hoy))
    if not periodos:
        return None
    meses, (inicio, fin) = 0, periodos[0]
    for otro_inicio, otro_fin in periodos[1:]:
        if otro_inicio <= fin:                  # se superponen: se unen
            fin = max(fin, otro_fin)
        else:
            meses += fin - inicio
            inicio, fin = otro_inicio, otro_fin
    meses += fin - inicio
    return math.floor(meses / 12 * 2) / 2       # hacia abajo, de medio año en medio año


def estimar_perfil(texto, hoy=None):
    """Lo que Euthetos propone a partir del CV; la persona lo confirma en pantalla."""
    return {
        "nivel": grado_del_cv(texto),
        "colegiado": bool(re.search(r"colegiad|colegiatura|n° de colegio|cap n|cip n|cal n", normalizar(texto))),
        "anios_experiencia": anios_de_experiencia(texto, hoy),
    }
