"""
Euthetos («apto», en griego antiguo)
Descubre en un minuto a qué convocatorias del Estado peruano puedes postular.

    streamlit run app.py

La persona escribe su carrera y adjunta su CV. La aplicación:
  1. lee el CV y propone grado y periodos de trabajo (la persona los confirma);
  2. compara ese perfil con cada oferta vigente de Talento Perú (reglas.py);
  3. ordena las ofertas por parecido con el CV (emparejar.py).

Los colores del tema están en .streamlit/config.toml; aquí solo los estilos propios.
"""

import hashlib
import html
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import cv
import emparejar
import reglas

CARPETA = Path(__file__).parent / "datos"
URL_TALENTO = "https://app.servir.gob.pe/DifusionOfertasExterno/faces/consultas/ofertas_laborales.xhtml"
SIN_EJEMPLO = "Ninguno"
CV_DE_EJEMPLO = {
    "Enfermería · Lucía, licenciada": ("enfermeria.txt", "Enfermería"),
    "Ingeniería Civil · Diego, bachiller": ("ingenieria_civil.txt", "Ingeniería Civil"),
    "Derecho · Valeria, abogada": ("derecho.txt", "Derecho"),
}
MAX_POR_PESTANA = 25
ETIQUETAS = {"ok": "Cumple", "revisar": "Revisar", "falta": "Falta"}
VEREDICTOS = {"verde": "Cumples lo medible", "amarillo": "Conviene revisar", "rojo": "Te falta un requisito"}

# Paleta (contraste de cada texto sobre su fondo comprobado: todos ≥ 5:1)
AZUL_NOCHE, AZUL, AZUL_SUAVE, DORADO = "#13284A", "#1F4E8C", "#EAF0F8", "#E9B44C"

st.set_page_config(page_title="Euthetos · Empleo público en el Perú", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container {max-width: 1100px; padding-top: 1.6rem; padding-bottom: 2rem;}

/* Cabecera */
.eu-hero {background: linear-gradient(135deg, #0F2240 0%, #1D3A68 55%, #1F4E8C 100%); border-radius: 16px;
          padding: 1.9rem 2.2rem 1.6rem; color: #DBE5F3; position: relative; overflow: hidden; margin-bottom: 1.4rem;}
.eu-hero::after {content: "εὔθετος"; position: absolute; right: 1.6rem; top: .4rem; font-family: "Montserrat";
                 font-weight: 800; font-size: 5.2rem; color: rgba(255,255,255,.06); letter-spacing: -.02em;}
.eu-eyebrow {font-size: .74rem !important; font-weight: 700; letter-spacing: .14em; text-transform: uppercase;
             color: #E9B44C; margin: 0 0 .35rem;}
.eu-marca {font-family: "Montserrat", sans-serif; font-size: 2.6rem !important; font-weight: 800; color: #FFFFFF;
           letter-spacing: -.02em; line-height: 1.05; margin: 0;}
.eu-lema {font-size: 1.12rem !important; color: #DBE5F3; margin: .45rem 0 1.2rem; max-width: 40rem; line-height: 1.5;}
.eu-lema b {color: #FFFFFF;}
.eu-cifras {display: grid; grid-template-columns: repeat(4, 1fr); gap: .7rem;}
.eu-cifra {background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.14); border-radius: 10px;
           padding: .65rem .9rem;}
.eu-cifra b {display: block; font-family: "Montserrat"; font-size: 1.45rem; font-weight: 700; color: #FFFFFF;}
.eu-cifra span {font-size: .8rem; color: #A9C6EE;}

/* Pasos de la portada */
.eu-pasos {display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: .4rem 0 1.4rem;}
.eu-paso {background: #FFFFFF; border: 1px solid #D5DEEA; border-top: 4px solid var(--c); border-radius: 12px;
          padding: 1.1rem 1.2rem 1.2rem; box-shadow: 0 1px 3px rgba(15,34,64,.06);}
.eu-num {display: inline-flex; align-items: center; justify-content: center; width: 2rem; height: 2rem;
         border-radius: 50%; background: var(--c); color: #FFFFFF; font-family: "Montserrat"; font-weight: 700;}
.eu-paso b {display: block; margin: .6rem 0 .3rem; font-family: "Montserrat"; color: #13284A; font-size: 1.02rem;}
.eu-paso span {font-size: .93rem; color: #4A5568; line-height: 1.5;}
.eu-paso span.eu-num {color: #FFFFFF; font-size: .95rem; line-height: 1;}

/* Títulos de sección */
.eu-seccion {font-family: "Montserrat", sans-serif; font-size: 1.18rem !important; font-weight: 700; color: #13284A;
             margin: 1.4rem 0 .2rem; display: flex; align-items: center; gap: .55rem;}
.eu-seccion::before {content: ""; width: .32rem; height: 1.15rem; border-radius: 3px; background: #E9B44C;}
.eu-nota {font-size: .87rem !important; color: #5B6678; line-height: 1.5;}

/* Resumen de resultados */
.eu-resumen {display: grid; grid-template-columns: repeat(4, 1fr); gap: .8rem; margin: .6rem 0 1rem;}
.eu-dato {background: var(--f); border: 1px solid var(--b); border-radius: 12px; padding: .85rem 1rem;}
.eu-dato b {display: block; font-family: "Montserrat"; font-size: 1.9rem; font-weight: 700; color: var(--t);
            line-height: 1.1;}
.eu-dato span {font-size: .86rem; color: #36404F; font-weight: 500;}

/* Pestañas como botones */
.stTabs [role="tablist"] {gap: .5rem; border-bottom: none; flex-wrap: wrap;}
.stTabs .react-aria-SelectionIndicator {display: none;}
.stTabs [data-testid="stTab"] {background: #FFFFFF; border: 1px solid #D5DEEA; border-radius: 999px;
                               padding: .4rem 1.05rem; height: auto;}
.stTabs [data-testid="stTab"] p {font-weight: 600; color: #36404F;}
.stTabs [data-testid="stTab"][aria-selected="true"] {background: #13284A; border-color: #13284A;}
.stTabs [data-testid="stTab"][aria-selected="true"] p {color: #FFFFFF;}

/* Cargador de archivos en español (el texto original de Streamlit está en inglés) */
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p {font-size: 0;}
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after {
  content: "Subir archivo"; font-size: .9rem;}
[data-testid="stFileUploaderDropzoneInstructions"] span {font-size: 0 !important;}
[data-testid="stFileUploaderDropzoneInstructions"] span::after {content: "Hasta 200 MB · PDF, DOCX o TXT";
  font-size: .78rem;}
[data-testid="stSidebar"] {min-width: 340px !important; width: 340px !important;}

/* Tarjetas de oferta */
[class*="st-key-oferta_"], .st-key-grafico {background: #FFFFFF; box-shadow: 0 1px 3px rgba(15,34,64,.07);}
[class*="st-key-oferta_"][class*="_verde"] {border-left: 5px solid #1E8A5A !important;}
[class*="st-key-oferta_"][class*="_amarillo"] {border-left: 5px solid #D4952B !important;}
[class*="st-key-oferta_"][class*="_rojo"] {border-left: 5px solid #C2493F !important;}
.eu-cabeza {display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;}
.eu-titulo {font-family: "Montserrat", sans-serif; font-size: 1.08rem !important; font-weight: 700; color: #13284A;
            margin: 0; line-height: 1.35;}
.eu-entidad {color: #4A5568; font-size: .92rem; margin: .15rem 0 .6rem;}
.eu-sello {flex: none; font-size: .74rem; font-weight: 700; border-radius: 999px; padding: .2rem .75rem;
           white-space: nowrap;}
.eu-sello.verde {background: #E3F4EC; color: #17694A;}
.eu-sello.amarillo {background: #FDF1DC; color: #8A5A00;}
.eu-sello.rojo {background: #FBE7E4; color: #9C3329;}
.eu-chips {margin-bottom: .35rem;}
.eu-chips span {display: inline-block; border-radius: 999px; padding: .14rem .7rem; font-size: .8rem;
                font-weight: 500; margin: 0 .35rem .35rem 0;}
.eu-chips .sueldo {background: #E3F4EC; color: #17694A;}
.eu-chips .cierre {background: #EAF0F8; color: #1F4E8C;}
.eu-chips .urgente {background: #FDF1DC; color: #8A5A00;}
.eu-chips .lugar {background: #EAF0F8; color: #1F4E8C;}
.eu-chips .regimen {background: #EEEAFB; color: #5B45B0;}
.eu-chips .afinidad {background: #13284A; color: #FFFFFF;}
.eu-motivo {display: flex; gap: .7rem; align-items: baseline; font-size: .93rem; color: #2E353A; margin: .3rem 0;}
.eu-estado {flex: none; width: 4.7rem; text-align: center; font-size: .7rem; font-weight: 700;
            letter-spacing: .04em; text-transform: uppercase; border-radius: 5px; padding: .14rem 0;}
.eu-estado.ok {background: #E3F4EC; color: #17694A;}
.eu-estado.revisar {background: #FDF1DC; color: #8A5A00;}
.eu-estado.falta {background: #FBE7E4; color: #9C3329;}
.eu-literal {font-size: .91rem; color: #36404F; line-height: 1.6; margin: 0 0 .6rem;}
.eu-literal b {color: #13284A;}

/* Barra lateral */
.eu-lateral {font-family: "Montserrat"; font-weight: 700; font-size: 1.2rem !important; color: #FFFFFF; margin: 0;}
.eu-lateral-nota {font-size: .82rem !important; color: #A9C6EE; margin: .15rem 0 .9rem; line-height: 1.45;}

/* Pie */
.eu-pie {background: #13284A; color: #C9D6EA; border-radius: 14px; padding: 1.1rem 1.4rem; margin-top: 2rem;
         font-size: .86rem; line-height: 1.55;}
.eu-pie b {color: #E9B44C;}

@media (max-width: 760px) {
  .eu-cifras, .eu-resumen {grid-template-columns: repeat(2, 1fr);}
  .eu-pasos {grid-template-columns: 1fr;}
  .eu-hero::after {display: none;}
  .eu-cabeza {flex-direction: column; gap: .3rem;}
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Texto: las entidades publican todo en mayúsculas, que cansa la vista
# ---------------------------------------------------------------------------
CONECTORES = {"de", "del", "la", "las", "el", "los", "y", "e", "en", "para", "a", "o", "u", "por", "con", "al"}
ROMANOS = {"i", "ii", "iii", "iv", "v", "vi"}


def legible(texto, como_nombre=False):
    """'ESPECIALISTA LEGAL I - TFL' -> 'Especialista legal I - TFL' (las siglas sin vocales se respetan)."""
    if not isinstance(texto, str):
        return ""
    # Algunas entidades publican Ñ donde iban comillas: «ÑPLATAFORMAS ... PAISÑ»
    if re.search(r"[A-Z]Ñ(\s|$|[,.)-])", texto):
        texto = re.sub(r"\bÑ(?=[A-ZÁÉÍÓÚ]{3})", "«", texto)
        texto = re.sub(r"(?<=[A-ZÁÉÍÓÚ])Ñ(?=\s|$|[,.)-])", "»", texto)
    palabras = []
    for posicion, palabra in enumerate(texto.split()):
        letras = re.sub(r"[^a-záéíóúñ]", "", palabra.lower())
        es_sigla = ((palabra.isupper() and 2 <= len(letras) <= 5 and not re.search(r"[aeiouáéíóú]", letras))
                    or re.fullmatch(r"(?:[A-ZÁÉÍÓÚÑ]\.)+[,;]?", palabra))           # «TFL», «A.I.S.»
        if letras in ROMANOS or es_sigla:
            palabras.append(palabra.upper())
        elif posicion == 0 or (como_nombre and letras not in CONECTORES):
            palabras.append(palabra.lower().capitalize() if palabra[0].isalpha() else palabra.lower().title())
        else:
            palabras.append(palabra.lower())
    return " ".join(palabras)


def en_oraciones(texto):
    """Pasa un requisito en mayúsculas a minúsculas, con mayúscula al empezar cada frase."""
    texto = re.sub(r"\s+", " ", texto.lower()).strip()
    return re.sub(r"(^|[.•:;]\s+|-\s+)([a-záéíóúñ])", lambda m: m.group(1) + m.group(2).upper(), texto)


def miles(numero):
    """3804 -> '3,804' (separador de miles como en el resto del curso)."""
    return f"{numero:,}"


# ---------------------------------------------------------------------------
# Datos: se cargan una sola vez
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Cargando las ofertas vigentes…")
def cargar_ofertas(hoy):
    df = pd.read_csv(CARPETA / "convocatorias.csv", dtype=str)
    df = df[df["fecha_fin"].fillna("9999") >= hoy].reset_index(drop=True)
    pedidos = pd.DataFrame([reglas.requisitos(oferta) for oferta in df.to_dict("records")])
    df = pd.concat([df, pedidos], axis=1)
    df["departamento"] = df["ubicacion"].fillna("Sin dato").str.split(" - ").str[0].str.title()
    df["remuneracion_soles"] = pd.to_numeric(df["remuneracion_soles"], errors="coerce")
    df["dias"] = (pd.to_datetime(df["fecha_fin"]) - pd.Timestamp(hoy)).dt.days
    return df


@st.cache_resource(show_spinner="Cargando el modelo de lenguaje (solo la primera vez)…")
def cargar_modelo():
    return emparejar.cargar_modelo()


@st.cache_data
def vectores_alineados(ids):
    """La matriz E en el mismo orden que la tabla de ofertas (o None si no está calculada)."""
    indice, E = emparejar.cargar_vectores()
    if indice is None or any(i not in indice for i in ids):
        return None
    return E[[indice[i] for i in ids]]


@st.cache_data(show_spinner="Comparando tu perfil con cada oferta…")
def evaluar(perfil_como_tupla, hoy):
    """Veredicto de cada oferta para un perfil. Se guarda para no repetirlo al mover un filtro."""
    perfil = dict(perfil_como_tupla)
    ofertas = cargar_ofertas(hoy)
    resultados = [reglas.veredicto(perfil, oferta, oferta) for oferta in ofertas.to_dict("records")]
    return ([r["color"] for r in resultados], [r["motivos"] for r in resultados],
            [r["carrera"] for r in resultados])


@st.cache_data(show_spinner="Buscando las ofertas más parecidas a tu currículo…")
def calcular_afinidad(carrera, texto_cv, ids):
    E = vectores_alineados(ids)
    if E is None:
        return None
    try:
        q = emparejar.vector_de_cv(cargar_modelo(), carrera, texto_cv)
    except Exception:            # sin modelo (p. ej., sin memoria en el servidor): se ordena solo por reglas
        return None
    return emparejar.afinidad(E, q)


hoy = datetime.now(ZoneInfo("America/Lima")).date().isoformat()
ofertas = cargar_ofertas(hoy)
corte = pd.to_datetime(ofertas["leido"]).max()

# ---------------------------------------------------------------------------
# Barra lateral: el perfil
# ---------------------------------------------------------------------------
# Un enlace como .../?demo=enfermeria abre la aplicación con ese CV ficticio ya cargado
demo = st.query_params.get("demo")
if demo and "ejemplo" not in st.session_state:
    coincidencias = [nombre for nombre, (archivo_cv, _) in CV_DE_EJEMPLO.items() if archivo_cv.startswith(demo)]
    if coincidencias:
        st.session_state["ejemplo"] = coincidencias[0]

with st.sidebar:
    st.markdown('<p class="eu-eyebrow">Paso 1 y 2</p><p class="eu-lateral">Tu perfil</p>'
                '<p class="eu-lateral-nota">Tu currículo se lee en el momento y no se guarda.</p>',
                unsafe_allow_html=True)
    zona_carrera = st.container()
    archivo = st.file_uploader("Currículo (PDF, Word o texto)", type=["pdf", "docx", "txt"])
    ejemplo = st.selectbox("O prueba con un currículo ficticio", [SIN_EJEMPLO] + list(CV_DE_EJEMPLO), key="ejemplo")
    zona_confirmar = st.container()

texto_cv, carrera_sugerida, aviso_cv = "", None, None
if archivo is not None:
    try:
        texto_cv = cv.leer_cv(archivo.name, archivo.getvalue())
    except Exception:
        aviso_cv = "No se pudo leer ese archivo. Prueba con un PDF con texto, un .docx o un .txt."
    if not aviso_cv and len(texto_cv.strip()) < 200:
        aviso_cv = "El archivo casi no tiene texto (¿es un PDF escaneado?). Súbelo en Word o como PDF con texto."
elif ejemplo != SIN_EJEMPLO:
    nombre_archivo, carrera_sugerida = CV_DE_EJEMPLO[ejemplo]
    texto_cv = (CARPETA / "cv_ejemplo" / nombre_archivo).read_text(encoding="utf-8")

# Cuando llega un CV nuevo, se proponen el grado y los periodos leídos de él
huella = hashlib.sha1(texto_cv.encode("utf-8")).hexdigest()[:12]
if st.session_state.get("huella_cv") != huella:
    estimado = cv.estimar_perfil(texto_cv) if texto_cv else {"nivel": None, "colegiado": False, "periodos": []}
    st.session_state["huella_cv"] = huella
    st.session_state["periodos"] = estimado["periodos"]
    st.session_state["suma_periodos"] = None
    st.session_state["nivel"] = reglas.NIVELES[estimado["nivel"] if estimado["nivel"] is not None else reglas.BACHILLER]
    st.session_state["colegiado"] = estimado["colegiado"]
    st.session_state["exp_general"] = st.session_state["exp_especifica"] = 0.0
    if carrera_sugerida:
        st.session_state["carrera"] = carrera_sugerida

with zona_carrera:
    carrera = st.text_input("Carrera", key="carrera", placeholder="Ej.: Contabilidad, Psicología…")

# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------
st.markdown(f"""
<div class="eu-hero">
  <p class="eu-eyebrow">Empleo público en el Perú · Datos oficiales de Talento Perú (SERVIR)</p>
  <p class="eu-marca">Euthetos</p>
  <p class="eu-lema">Escribe tu carrera, adjunta tu currículo y descubre en un minuto <b>a qué convocatorias del
  Estado puedes postular</b>, con cada requisito tal como lo publicó la entidad.</p>
  <div class="eu-cifras">
    <div class="eu-cifra"><b>{miles(len(ofertas))}</b><span>ofertas vigentes</span></div>
    <div class="eu-cifra"><b>{miles(ofertas['institucion'].nunique())}</b><span>entidades públicas</span></div>
    <div class="eu-cifra"><b>{ofertas['departamento'].nunique()}</b><span>departamentos</span></div>
    <div class="eu-cifra"><b>{corte:%d/%m}</b><span>actualizado a las {corte:%H:%M}</span></div>
  </div>
</div>""", unsafe_allow_html=True)
if aviso_cv:
    st.warning(aviso_cv)

if not carrera.strip():
    st.markdown("""
<div class="eu-pasos">
  <div class="eu-paso" style="--c:#1F4E8C"><span class="eu-num">1</span><b>Escribe tu carrera</b>
    <span>En el panel azul de la izquierda. Sirve cualquier carrera universitaria o técnica.</span></div>
  <div class="eu-paso" style="--c:#D4952B"><span class="eu-num">2</span><b>Adjunta tu currículo</b>
    <span>Se leen tu grado y tus periodos de trabajo. Tú decides cuáles cuentan como experiencia.</span></div>
  <div class="eu-paso" style="--c:#1E8A5A"><span class="eu-num">3</span><b>Revisa tus convocatorias</b>
    <span>Cada oferta indica si cumples lo que pide, qué te falta y cuándo cierra.</span></div>
</div>
<p class="eu-nota"><i>Euthetos</i> (εὔθετος) significa «apto» en griego antiguo. ¿No tienes tu currículo a la mano?
Elige uno ficticio en el panel de la izquierda.</p>""", unsafe_allow_html=True)
    st.stop()

# ---------------------------------------------------------------------------
# Periodos de trabajo leídos del CV: la persona decide cuáles cuentan
# ---------------------------------------------------------------------------
periodos = st.session_state.get("periodos", [])
if periodos:
    st.markdown('<p class="eu-seccion">Tu experiencia, según tu currículo</p>'
                '<p class="eu-nota">Desmarca los periodos que no puedas acreditar con una constancia o un certificado. '
                'Los periodos que se superponen se cuentan una sola vez.</p>', unsafe_allow_html=True)
    tabla_periodos = pd.DataFrame(periodos).assign(contar=True)
    editada = st.data_editor(
        tabla_periodos[["contar", "periodo", "meses", "detalle"]],
        column_config={"contar": st.column_config.CheckboxColumn("Contar", width="small"),
                       "periodo": st.column_config.TextColumn("Periodo", width="medium"),
                       "meses": st.column_config.NumberColumn("Meses", width="small"),
                       "detalle": st.column_config.TextColumn("Línea de tu currículo", width="large")},
        disabled=["periodo", "meses", "detalle"], hide_index=True, use_container_width=True,
        key=f"editor_{huella}")
    elegidos = [p for p, contar in zip(periodos, editada["contar"]) if contar]
    suma = cv.sumar_periodos(elegidos)
    if st.session_state.get("suma_periodos") != suma:           # cambió la selección: se actualiza el perfil
        st.session_state["suma_periodos"] = suma
        st.session_state["exp_general"] = st.session_state["exp_especifica"] = suma
elif texto_cv and not aviso_cv:
    st.info("No se encontraron periodos de trabajo en tu currículo. Indica tus años de experiencia en el panel izquierdo.")

with zona_confirmar:
    st.divider()
    nivel = st.selectbox("Grado más alto", reglas.NIVELES, key="nivel")
    exp_general = st.number_input("Años de experiencia laboral", 0.0, 50.0, step=0.5, format="%.1f", key="exp_general")
    exp_especifica = st.number_input("De ellos, en tu especialidad", 0.0, 50.0, step=0.5, format="%.1f",
                                     key="exp_especifica")
    colegiado = st.checkbox("Colegiatura y habilitación vigentes", key="colegiado")

perfil = {"carrera": carrera.strip(), "nivel": reglas.NIVELES.index(nivel), "colegiado": colegiado,
          "exp_general": exp_general, "exp_especifica": min(exp_especifica, exp_general)}

# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------
colores, motivos, estado_carrera = evaluar(tuple(sorted(perfil.items())), hoy)
tabla = ofertas.assign(color=colores, motivos=motivos, estado_carrera=estado_carrera)
tabla["menciona_carrera"] = tabla["estado_carrera"] == "si"

afinidad = calcular_afinidad(perfil["carrera"], texto_cv, tuple(ofertas["id"]))
tabla["afinidad"] = 0.0 if afinidad is None else afinidad
# La similitud no tiene una escala fija: lo que importa es el orden entre ofertas
tabla["puesto_afinidad"] = tabla["afinidad"].rank(ascending=False, pct=True)

st.markdown('<p class="eu-seccion">Tus convocatorias</p>', unsafe_allow_html=True)
f1, f2, f3 = st.columns([3, 2, 3])
departamentos = f1.multiselect("Departamento", sorted(tabla["departamento"].unique()), placeholder="Todo el Perú")
sueldo_minimo = f2.number_input("Remuneración mínima (S/)", 0, 20000, 0, step=500)
with f3:
    solo_afines = st.toggle("Solo las más parecidas a mi currículo", value=False,
                            help="Muestra únicamente el 20% de ofertas con mayor parecido.")
    sin_carrera = st.toggle("Incluir puestos que no piden carrera", value=perfil["nivel"] <= reglas.TECNICO,
                            help="Por ejemplo, los que solo piden secundaria completa.")

vista = tabla
if not sin_carrera:
    vista = vista[vista["estado_carrera"] != "sin_carrera"]
if departamentos:
    vista = vista[vista["departamento"].isin(departamentos)]
if sueldo_minimo:
    vista = vista[vista["remuneracion_soles"] >= sueldo_minimo]
if solo_afines:
    vista = vista[vista["puesto_afinidad"] <= 0.20]

verdes, amarillas, rojas = (vista[vista["color"] == c] for c in ("verde", "amarillo", "rojo"))
posibles = pd.concat([verdes, amarillas])
por_cerrar = int((posibles["dias"] <= 3).sum())
st.markdown(f"""
<div class="eu-resumen">
  <div class="eu-dato" style="--f:#E3F4EC;--b:#BFE3D0;--t:#17694A"><b>{miles(len(verdes))}</b><span>Cumples lo medible</span></div>
  <div class="eu-dato" style="--f:#FDF1DC;--b:#F2D9A8;--t:#8A5A00"><b>{miles(len(amarillas))}</b><span>Conviene revisar</span></div>
  <div class="eu-dato" style="--f:#FBE7E4;--b:#F1C5BF;--t:#9C3329"><b>{miles(len(rojas))}</b><span>Te falta un requisito</span></div>
  <div class="eu-dato" style="--f:#EAF0F8;--b:#C9D6EA;--t:#1F4E8C"><b>{miles(por_cerrar)}</b><span>Cierran en 3 días o menos</span></div>
</div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Gráfico: dónde están las oportunidades (verdes + amarillas) por departamento
# ---------------------------------------------------------------------------
def grafico_departamentos(posibles):
    conteo = posibles["departamento"].value_counts().head(10).sort_values()
    figura = go.Figure(go.Bar(
        x=conteo.values, y=conteo.index, orientation="h", marker=dict(color=AZUL, cornerradius=4),
        width=0.62, text=[miles(v) for v in conteo.values], textposition="outside", cliponaxis=False,
        textfont=dict(color="#36404F", size=12),
        hovertemplate="<b>%{y}</b><br>%{x:,} ofertas en las que cumples o conviene revisar<extra></extra>"))
    figura.update_layout(
        height=max(180, 34 * len(conteo) + 40), margin=dict(l=0, r=36, t=6, b=6),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", font=dict(family="Inter, sans-serif", color="#36404F"),
        xaxis=dict(showgrid=True, gridcolor="#EEF2F7", zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, tickfont=dict(size=12.5, color="#1B2433")),
        hoverlabel=dict(bgcolor="#13284A", font_color="#FFFFFF", bordercolor="#13284A"), bargap=0.35)
    return figura


if not posibles.empty and posibles["departamento"].nunique() > 1:
    with st.container(border=True, key="grafico"):
        st.markdown('<p class="eu-titulo">Dónde están tus oportunidades</p>'
                    '<p class="eu-nota" style="margin:.1rem 0 .3rem">Ofertas en las que cumples lo medible o conviene '
                    'revisar, por departamento (los 10 con más ofertas).</p>', unsafe_allow_html=True)
        st.plotly_chart(grafico_departamentos(posibles), use_container_width=True,
                        config={"displayModeBar": False})


def nivel_de_afinidad(puesto):
    return "muy alta" if puesto <= 0.05 else "alta" if puesto <= 0.20 else "media" if puesto <= 0.50 else "baja"


def tarjeta(oferta):
    """Una oferta: puesto, entidad, sello del veredicto, datos clave, motivos y, plegado, el texto de la entidad."""
    sueldo = (f"S/ {oferta['remuneracion_soles']:,.0f} al mes"
              if oferta["remuneracion_soles"] == oferta["remuneracion_soles"] else "Sueldo sin dato")
    dias = oferta["dias"]
    cierre = "Cierra hoy" if dias == 0 else "Cierra mañana" if dias == 1 else f"Cierra en {dias} días"
    chips = [f'<span class="sueldo">{sueldo}</span>',
             f'<span class="{"urgente" if dias <= 3 else "cierre"}">{cierre}</span>',
             f'<span class="lugar">{html.escape(legible(oferta["ubicacion"], True))}</span>',
             f'<span class="regimen">{html.escape(oferta["regimen"])}</span>']
    if afinidad is not None:
        referencia = "currículo" if texto_cv else "carrera"
        chips.append(f'<span class="afinidad">Afinidad con tu {referencia}: '
                     f'{nivel_de_afinidad(oferta["puesto_afinidad"])}</span>')
    filas = "".join(f'<div class="eu-motivo"><span class="eu-estado {estado}">{ETIQUETAS[estado]}</span>'
                    f"<span>{html.escape(texto)}</span></div>" for estado, texto in oferta["motivos"])
    with st.container(border=True, key=f"oferta_{oferta['id']}_{oferta['color']}"):
        st.markdown(f'<div class="eu-cabeza"><div><div class="eu-titulo">{html.escape(legible(oferta["titulo"]))}</div>'
                    f'<div class="eu-entidad">{html.escape(legible(oferta["institucion"], True))}</div></div>'
                    f'<span class="eu-sello {oferta["color"]}">{VEREDICTOS[oferta["color"]]}</span></div>'
                    f'<div class="eu-chips">{"".join(chips)}</div>{filas}', unsafe_allow_html=True)
        with st.expander("Requisitos publicados por la entidad"):
            secciones = [("Formación", "formacion"), ("Experiencia", "experiencia"),
                         ("Especialización", "especializacion"), ("Conocimientos", "conocimientos")]
            st.markdown("".join(f'<p class="eu-literal"><b>{nombre}.</b> {html.escape(en_oraciones(oferta[campo]))}</p>'
                                for nombre, campo in secciones
                                # algunas entidades llenan la sección con guiones: se omite
                                if isinstance(oferta[campo], str) and re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", oferta[campo]))
                        + f'<p class="eu-nota">Convocatoria {html.escape(str(oferta["numero_convocatoria"]))} · '
                        + (f'Aviso N.° {oferta["n_aviso"]} · ' if isinstance(oferta["n_aviso"], str) else "")
                        + f'{oferta["vacantes"]} vacante(s) · '
                          f'Publicada del {pd.Timestamp(oferta["fecha_inicio"]):%d/%m/%Y} al '
                          f'{pd.Timestamp(oferta["fecha_fin"]):%d/%m/%Y}. '
                          "El texto se muestra en minúsculas para facilitar la lectura.</p>", unsafe_allow_html=True)
            botones = st.columns([2, 2, 5])
            if isinstance(oferta["enlace_bases"], str):
                botones[0].link_button("Bases de la entidad", oferta["enlace_bases"], type="primary",
                                       use_container_width=True)
            botones[1].link_button("Abrir Talento Perú", URL_TALENTO, use_container_width=True)


def mostrar(grupo, explicacion, vacio):
    """Lista de ofertas de un color: primero las que nombran la carrera y, dentro de ellas,
    de la más parecida al CV a la menos parecida."""
    st.markdown(f'<p class="eu-nota">{explicacion}</p>', unsafe_allow_html=True)
    if grupo.empty:
        st.info(vacio)
        return
    grupo = grupo.sort_values(["menciona_carrera", "afinidad", "dias"], ascending=[False, False, True])
    if len(grupo) > MAX_POR_PESTANA:
        st.markdown(f'<p class="eu-nota">Se muestran las {MAX_POR_PESTANA} más idóneas de {miles(len(grupo))}: primero '
                    "las que nombran tu carrera y, entre ellas, las más parecidas a tu currículo. Usa los filtros o "
                    "descarga la lista completa al final.</p>", unsafe_allow_html=True)
    for oferta in grupo.head(MAX_POR_PESTANA).to_dict("records"):
        tarjeta(oferta)


pestana_verde, pestana_amarilla, pestana_roja = st.tabs([
    f"Cumples lo medible · {miles(len(verdes))}", f"Conviene revisar · {miles(len(amarillas))}",
    f"Te falta un requisito · {miles(len(rojas))}"])
with pestana_verde:
    mostrar(verdes, "Cumples la carrera, el grado y los años de experiencia que se pudieron medir.",
            "Ninguna oferta cumple todo lo medible con este perfil. Mira la pestaña «Conviene revisar».")
with pestana_amarilla:
    mostrar(amarillas, "Nada te descarta, pero hay algo que debes leer tú: carreras afines, colegiatura, "
                       "posgrado o un texto poco claro.", "No hay ofertas por revisar.")
with pestana_roja:
    mostrar(rojas, "Te falta al menos un requisito medible. Sirve para saber qué te separa de cada puesto.",
            "No hay ofertas en esta categoría.")

descarga = posibles.sort_values(["menciona_carrera", "afinidad"], ascending=False)
st.download_button("Descargar mis convocatorias (CSV)",
                   descarga[["color", "titulo", "institucion", "ubicacion", "regimen", "remuneracion", "fecha_fin",
                             "formacion", "experiencia", "numero_convocatoria", "n_aviso", "enlace_bases"]]
                   .to_csv(index=False).encode("utf-8-sig"),
                   file_name="mis_convocatorias_euthetos.csv", mime="text/csv", type="primary")

st.markdown(
    '<div class="eu-pie"><b>Euthetos</b> compara solo lo medible (carrera, grado y años de experiencia) y muestra '
    "cada requisito tal como lo publicó la entidad. Quien decide si una persona es apta es el comité de selección: "
    "lee siempre las bases antes de postular. Fuente: Talento Perú (SERVIR), portal oficial de ofertas laborales "
    f"del Estado, leído hasta el {corte:%d/%m/%Y} a las {corte:%H:%M}.</div>", unsafe_allow_html=True)
