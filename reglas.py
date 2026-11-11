"""
Reglas de encaje: comparan lo que pide una oferta con el perfil de la persona.

Aquí no hay inteligencia artificial: son reglas escritas a mano sobre el texto
que publica cada entidad en Talento Perú. Por eso el resultado siempre se
muestra junto al texto literal del requisito, para que la persona lo compruebe.

    veredicto(perfil, oferta) -> {"color": "verde" | "amarillo" | "rojo", "motivos": [...]}

El veredicto habla solo de lo que se puede medir (carrera, grado y años de
experiencia). Quien decide si alguien es apto es el comité de selección.
"""

import re
import unicodedata

# Del grado más bajo al más alto. La posición en la lista es el "nivel".
NIVELES = [
    "Secundaria completa",
    "Técnico (egresado o titulado)",
    "Estudiante universitario",
    "Egresado universitario",
    "Bachiller",
    "Título profesional o licenciatura",
    "Maestría",
    "Doctorado",
]
SECUNDARIA, TECNICO, ESTUDIANTE, EGRESADO, BACHILLER, TITULO, MAESTRIA, DOCTORADO = range(8)


def normalizar(texto):
    """Minúsculas y sin tildes: 'Ciencia Política' -> 'ciencia politica'."""
    if not texto or texto != texto:               # None, "" o NaN
        return ""
    texto = unicodedata.normalize("NFD", str(texto).lower())
    texto = "".join(letra for letra in texto if unicodedata.category(letra) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


# ---------------------------------------------------------------------------
# 1. Grado que pide la oferta
# ---------------------------------------------------------------------------
PATRONES_NIVEL = [
    (SECUNDARIA, r"secundari[ao]|segundaria|secuandria"),
    (TECNICO, r"tecnic[oa]s?\b|instituto"),
    (ESTUDIANTE, r"estudiante|ultimo ciclo|ultimos ciclos|ciclo academico|estudios universitarios"),
    (EGRESADO, r"egresad[oa]"),
    (BACHILLER, r"bachiller"),
    # Los nombres de profesión ("ingeniero", "enfermera", "obstetra") también implican título profesional
    (TITULO, r"titul[oa]|licenciad[oa]|licenciatura|abogad[oa]|medico|cirujano|contador publico|"
             r"\bingenier[oa]s?\b|\benfermer[oa]s?\b|obstetra|psicolog[oa]s?\b|nutricionista|economista|"
             r"arquitect[oa]s?\b|odontolog[oa]s?\b|biolog[oa]s?\b|veterinari[oa]s?\b|quimico farmaceutic"),
]
PATRON_POSGRADO = r"maestr|magister|\bmaster\b|doctorado|grado de doctor"
PATRON_COLEGIATURA = r"colegiad|colegiatura|habilitad|habilitacion"


def nivel_exigido(formacion):
    """Lee el grado mínimo que pide la sección "Formación" de una oferta.

    Si el texto ofrece alternativas ("título técnico o egresado universitario"),
    vale la más baja. La maestría y la colegiatura se devuelven aparte, porque
    a veces son obligatorias y a veces solo deseables.
    """
    texto = normalizar(formacion)
    resultado = {"nivel": None, "pide_posgrado": False, "pide_colegiatura": False}
    if not texto:
        return resultado

    # "Título técnico" y "egresado de carrera técnica" son nivel técnico, no título profesional
    solo_tecnico = "tecnic" in texto and "universit" not in texto and "bachiller" not in texto
    sin_titulo_tecnico = re.sub(r"titul[oa]s?( profesional)?( de)? tecnic[oa]s?", "tecnico", texto)

    encontrados = []
    for nivel, patron in PATRONES_NIVEL:
        if re.search(patron, sin_titulo_tecnico):
            if solo_tecnico and nivel in (EGRESADO, TITULO):
                continue
            encontrados.append(nivel)

    resultado["pide_posgrado"] = bool(re.search(PATRON_POSGRADO, texto))
    resultado["pide_colegiatura"] = bool(re.search(PATRON_COLEGIATURA, texto))
    if encontrados:
        resultado["nivel"] = min(encontrados)
    elif resultado["pide_posgrado"]:
        resultado["nivel"] = DOCTORADO if "doctor" in texto and "maestr" not in texto else MAESTRIA
    return resultado


# ---------------------------------------------------------------------------
# 2. ¿La oferta menciona la carrera?
# ---------------------------------------------------------------------------
# Otras formas en que las entidades escriben una misma carrera (lista ampliable)
SINONIMOS = {
    "derecho": ["abogad", "ciencias juridicas"],
    "medicina": ["medico", "medicina humana"],
    "contabilidad": ["contador", "ciencias contables"],
    "enfermeria": ["enfermer"],
    "psicologia": ["psicolog"],
    "educacion": ["docente", "profesor", "pedagog"],
    "ciencia politica": ["ciencias politicas", "politolog"],
    "comunicaciones": ["comunicacion", "periodis"],
    "ciencias de la comunicacion": ["comunicacion", "periodis"],
    "trabajo social": ["trabajador social", "trabajadora social"],
    "ingenieria de sistemas": ["ingenieria informatica", "ingenieria de software", "computacion"],
    "ingenieria informatica": ["ingenieria de sistemas", "ingenieria de software", "computacion"],
    "obstetricia": ["obstetra"],
    "nutricion": ["nutricionista"],
    "farmacia": ["quimico farmaceutic", "farmacia y bioquimica"],
    "arquitectura": ["arquitect"],
    "sociologia": ["sociolog"],
    "antropologia": ["antropolog"],
    "economia": ["economista"],
    "administracion": ["administrador", "ciencias administrativas"],
}
PALABRAS_VACIAS = {"de", "del", "la", "las", "el", "los", "y", "e", "en", "con"}
PATRON_AFINES = r"\bafin(es)?\b|a fines|carreras? similares|ramas? afines"
PATRON_CUALQUIER_CARRERA = r"cualquier (carrera|especialidad|profesion)|todas las carreras|carreras? en general"


def patron_de_carrera(carrera):
    """'Ciencia Política' -> expresión que acepta 'ciencias políticas', 'ciencia política'..."""
    palabras = [p for p in normalizar(carrera).split() if p not in PALABRAS_VACIAS]
    raices = [re.escape(re.sub(r"(as|os|es|a|o|s)$", "", p) if len(p) > 5 else p) + r"\w*" for p in palabras]
    return r"\b" + r"\s+(?:(?:de|del|la|las|el|los|y|e|en)\s+)*".join(raices) if raices else None


def carrera_mencionada(carrera, formacion, nivel=None):
    """Devuelve 'si', 'afines', 'no' o 'sin_carrera' (la oferta no pide una carrera en particular)."""
    texto = normalizar(formacion)
    if not texto or not normalizar(carrera):
        return "sin_dato"
    patrones = [patron_de_carrera(carrera)] + [r"\b" + re.escape(s) for s in SINONIMOS.get(normalizar(carrera), [])]
    if any(re.search(p, texto) for p in patrones if p):
        return "si"
    if re.search(PATRON_CUALQUIER_CARRERA, texto) or nivel == SECUNDARIA:
        return "sin_carrera"
    if re.search(PATRON_AFINES, texto):
        return "afines"
    return "no"


# ---------------------------------------------------------------------------
# 3. Años de experiencia que pide la oferta
# ---------------------------------------------------------------------------
NUMEROS_EN_LETRAS = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
                     "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
                     "once": 11, "doce": 12, "quince": 15, "dieciocho": 18, "veinticuatro": 24}
# "03 años", "(02) años", "dos (02) años", "seis meses", "1.5 años", "8.00 año(s)"
PATRON_DURACION = re.compile(
    r"(?<![a-z0-9.,])(\(?\s*\d{1,2}(?:[.,]\d{1,2})?\s*\)?|"
    + "|".join(sorted(NUMEROS_EN_LETRAS, key=len, reverse=True))
    + r")\s*\+?\s*(?:\(\s*\d{1,2}\s*\)\s*)?(anos?|meses|mes)(?=minim|[^a-z]|$)"
)
NEGACIONES = ["sin experiencia", "no requiere", "no se requiere", "no indispensable",
              "no es indispensable", "no necesaria", "no es necesaria", "con o sin", "no aplica"]
SENALES_ESPECIFICA = ["especific", "en la funcion", "en el puesto", "en la materia",
                      "funcion o materia", "funcion y/o materia", "funciones similares",
                      "funciones equivalentes", "puestos similares"]


def _a_anios(coincidencia):
    numero = coincidencia.group(1).strip("() ").replace(",", ".")
    valor = float(numero) if numero[0].isdigit() else NUMEROS_EN_LETRAS[numero]
    return valor / 12 if coincidencia.group(2).startswith("mes") else valor


def experiencia_exigida(experiencia):
    """Años de experiencia GENERAL y ESPECÍFICA que pide la sección "Experiencia".

    Se toma la primera duración de cada frase: en "6 meses en los últimos 3 años"
    lo pedido son los 6 meses. Si varias frases hablan de lo mismo, vale la mayor.
    """
    resultado = {"general": None, "especifica": None}
    texto = normalizar(experiencia)
    if not texto:
        return resultado

    texto = texto.replace("esperiencia", "experiencia")          # errata frecuente
    # Se corta en viñetas, puntos, comas y ";", y antes de "experiencia general/específica"
    # (salvo en "años de experiencia general", donde el número va delante):
    # "02 años de experiencia general, 01 año de experiencia específica" son dos frases
    separador = (r"\s*(?:•|;|\||:\s*-|\.\s|,\s|\s-\s|\sy\s+(?=experiencia)|"
                 r"(?<!\sde)\s+(?=experiencia\s+(?:laboral\s+)?(?:general|especifica)))\s*")
    tipo = "general"
    for frase in re.split(separador, texto):
        if "deseable" in frase or not frase:
            continue
        # Una frase sin la palabra "experiencia" sigue hablando de lo mismo que la anterior
        if any(s in frase for s in SENALES_ESPECIFICA):
            tipo = "especifica"
        elif "experiencia" in frase:
            tipo = "general"
        # "29 años de edad" no es experiencia
        validas = [m for m in PATRON_DURACION.finditer(frase)
                   if not frase[m.end(): m.end() + 10].strip().startswith("de edad")]
        if validas:
            anios = _a_anios(validas[0])
            if anios > 20:
                continue
        elif any(n in frase for n in NEGACIONES):
            anios = 0.0                                   # "no requiere experiencia"
        else:
            continue
        if resultado[tipo] is None or anios > resultado[tipo]:
            resultado[tipo] = round(anios, 2)
    return resultado


# ---------------------------------------------------------------------------
# 4. Régimen laboral (para mostrar que no son solo CAS)
# ---------------------------------------------------------------------------
REGIMENES = [
    (r"practica", "Prácticas (D. Leg. 1401)"),
    (r"1057", "CAS (D. Leg. 1057)"),
    (r"\b728\b", "D. Leg. 728"),
    (r"\b276\b", "D. Leg. 276"),
    (r"30057", "Ley 30057 (Servicio Civil)"),
    (r"1024|gerente publico", "Gerentes públicos (D. Leg. 1024)"),
    (r"29944|magisterial", "Reforma magisterial (Ley 29944)"),
    (r"30220|docentes? universitari", "Docencia universitaria (Ley 30220)"),
    (r"29277|jueces", "Carrera judicial (Ley 29277)"),
    (r"1153|23536", "Salud (D. Leg. 1153)"),
]


def regimen(numero_convocatoria):
    texto = normalizar(numero_convocatoria)
    for patron, nombre in REGIMENES:
        if re.search(patron, texto):
            return nombre
    return "Otro régimen"


# ---------------------------------------------------------------------------
# 5. El veredicto
# ---------------------------------------------------------------------------
def _anios(valor):
    """1.5 -> '1.5 años'; 0.5 -> '6 meses' (menos de un año se dice en meses)."""
    if 0 < valor < 1:
        meses = round(valor * 12)
        return f"{meses} mes" + ("" if meses == 1 else "es")
    return f"{valor:g} año" + ("" if valor == 1 else "s")


def requisitos(oferta):
    """Lo que pide una oferta, leído una sola vez: grado, posgrado, colegiatura, experiencia y régimen."""
    pedido = nivel_exigido(oferta.get("formacion"))
    exp = experiencia_exigida(oferta.get("experiencia"))
    return {"nivel_pedido": pedido["nivel"], "pide_posgrado": pedido["pide_posgrado"],
            "pide_colegiatura": pedido["pide_colegiatura"],
            "exp_general_pedida": exp["general"], "exp_especifica_pedida": exp["especifica"],
            "regimen": regimen(oferta.get("numero_convocatoria"))}


def veredicto(perfil, oferta, pedido=None):
    """Compara un perfil con una oferta.

    perfil: {"carrera", "nivel" (posición en NIVELES), "colegiado", "exp_general", "exp_especifica"}
    oferta: fila con "formacion", "experiencia" y "numero_convocatoria"
    pedido: resultado de requisitos(oferta), si ya se calculó antes
    Devuelve el color y los motivos; cada motivo es (estado, texto), con estado
    "ok", "revisar" o "falta".
    """
    pedido = pedido or requisitos(oferta)
    nivel = pedido["nivel_pedido"]
    # En una tabla de pandas el dato que falta llega como NaN y los enteros como decimales
    nivel = None if nivel is None or nivel != nivel else int(nivel)
    motivos = []

    # Carrera
    carrera = carrera_mencionada(perfil["carrera"], oferta.get("formacion"), nivel)
    if carrera == "si":
        motivos.append(("ok", f"La formación pedida menciona tu carrera ({perfil['carrera']})."))
    elif carrera == "sin_carrera":
        motivos.append(("ok", "No pide una carrera en particular."))
    elif carrera == "afines":
        motivos.append(("revisar", 'No nombra tu carrera, pero admite "carreras afines": revisa si la tuya lo es.'))
    elif carrera == "no":
        motivos.append(("falta", f"La formación pedida no menciona tu carrera ({perfil['carrera']})."))
    else:
        motivos.append(("revisar", "La oferta no publica la formación pedida."))

    # Grado
    if nivel is None:
        motivos.append(("revisar", "No se pudo leer el grado que pide: revisa el texto."))
    elif pedido["regimen"].startswith("Prácticas") and perfil["nivel"] >= BACHILLER:
        motivos.append(("revisar", "Es una práctica: suele ser solo para estudiantes o egresados recientes."))
    else:
        estado = "ok" if perfil["nivel"] >= nivel else "falta"
        motivos.append((estado, f"Pide como mínimo \"{NIVELES[nivel]}\" y tú indicaste \"{NIVELES[perfil['nivel']]}\"."))
    if pedido["pide_posgrado"] and perfil["nivel"] < MAESTRIA and (nivel or 0) < MAESTRIA:
        motivos.append(("revisar", "Menciona estudios de posgrado: revisa si son obligatorios."))
    if pedido["pide_colegiatura"] and not perfil.get("colegiado"):
        motivos.append(("revisar", "Menciona colegiatura o habilitación profesional."))

    # Experiencia
    for clave_pedida, clave_perfil, nombre in (("exp_general_pedida", "exp_general", "general"),
                                               ("exp_especifica_pedida", "exp_especifica", "específica")):
        pide, tiene = pedido[clave_pedida], perfil[clave_perfil]
        if pide is None or pide != pide:                       # sin dato (None o NaN)
            continue
        estado = "ok" if tiene >= pide else "falta"
        motivos.append((estado, f"Pide {_anios(pide)} de experiencia {nombre} y tú indicaste {_anios(tiene)}."))
    if not any("experiencia" in texto for _, texto in motivos):
        motivos.append(("revisar", "No se pudo leer cuánta experiencia pide: revisa el texto."))

    estados = {estado for estado, _ in motivos}
    color = "rojo" if "falta" in estados else "amarillo" if "revisar" in estados else "verde"
    return {"color": color, "motivos": motivos, "carrera": carrera}
