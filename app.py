"""
Euthetos («apto», en griego antiguo)
Descubre en un minuto a qué convocatorias del Estado peruano puedes postular.

    streamlit run app.py

La persona escribe su carrera y adjunta su CV. La aplicación:
  1. lee el CV y propone grado y periodos de trabajo (la persona los confirma);
  2. compara ese perfil con cada oferta vigente de Talento Perú (reglas.py);
  3. ordena las ofertas por parecido con el CV (emparejar.py).
"""

import hashlib
import html
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
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

st.set_page_config(page_title="Euthetos · Empleo público", layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------------------------
# Estilo: colores apagados, sin íconos, texto cómodo de leer
# ---------------------------------------------------------------------------
st.markdown("""
<style>
.block-container {max-width: 1060px; padding-top: 2.4rem; padding-bottom: 3rem;}
.eu-marca {font-size: 2.1rem !important; font-weight: 700; letter-spacing: -0.02em; color: #1F4E5F; margin: 0; line-height: 1.1;}
.eu-lema {color: #5B6670; font-size: 1.08rem !important; margin: .35rem 0 1.4rem;}
.eu-seccion {font-size: .78rem; font-weight: 650; letter-spacing: .08em; text-transform: uppercase;
             color: #7A848C; margin: 1.6rem 0 .6rem;}
.eu-resumen {display: grid; grid-template-columns: repeat(4, 1fr); gap: .8rem; margin: .4rem 0 1.2rem;}
.eu-dato {background: #FFFFFF; border: 1px solid #E3E0D8; border-left: 4px solid var(--c); border-radius: 8px;
          padding: .8rem 1rem;}
.eu-dato b {display: block; font-size: 1.65rem; font-weight: 650; color: #22272B; line-height: 1.15;}
.eu-dato span {font-size: .86rem; color: #5B6670;}
.eu-pasos {display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 1rem 0 1.6rem;}
.eu-paso {background: #FFFFFF; border: 1px solid #E3E0D8; border-radius: 8px; padding: 1.1rem 1.2rem;}
.eu-paso i {font-style: normal; font-size: .8rem; font-weight: 650; color: #1F4E5F; letter-spacing: .06em;}
.eu-paso b {display: block; margin: .25rem 0 .3rem; color: #22272B;}
.eu-paso span {font-size: .92rem; color: #5B6670; line-height: 1.45;}
.eu-titulo {font-size: 1.08rem !important; font-weight: 650; color: #22272B; margin: 0; line-height: 1.35;}
.eu-entidad {color: #5B6670; font-size: .9rem; margin: .15rem 0 .55rem;}
.eu-chips span {display: inline-block; background: #F1EFE9; color: #3D464D; border-radius: 999px;
                padding: .12rem .7rem; font-size: .8rem; margin: 0 .35rem .35rem 0;}
.eu-chips .urgente {background: #F6EEDC; color: #8A5E10;}
.eu-motivo {display: flex; gap: .7rem; align-items: baseline; font-size: .93rem; color: #2E353A; margin: .28rem 0;}
.eu-estado {flex: none; width: 4.6rem; text-align: center; font-size: .7rem; font-weight: 650;
            letter-spacing: .04em; text-transform: uppercase; border-radius: 4px; padding: .12rem 0;}
.eu-estado.ok {background: #E4F0EA; color: #256B4D;}
.eu-estado.revisar {background: #F6EEDC; color: #8A5E10;}
.eu-estado.falta {background: #F6E6E3; color: #9C3D34;}
.eu-literal {font-size: .9rem; color: #3D464D; line-height: 1.55; margin: 0 0 .6rem;}
.eu-literal b {color: #22272B;}
.eu-nota {font-size: .86rem !important; color: #6E7880; line-height: 1.5;}
[class*="st-key-oferta_"] {background: #FFFFFF;}
@media (max-width: 760px) {.eu-resumen {grid-template-columns: repeat(2, 1fr);} .eu-pasos {grid-template-columns: 1fr;}}
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
        es_sigla = palabra.isupper() and 2 <= len(letras) <= 5 and not re.search(r"[aeiouáéíóú]", letras)
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
    q = emparejar.vector_de_cv(cargar_modelo(), carrera, texto_cv)
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
    st.markdown("### Tu perfil")
    zona_carrera = st.container()
    archivo = st.file_uploader("Currículo (PDF, Word o texto)", type=["pdf", "docx", "txt"])
    st.caption("Tu currículo se lee en el momento y no se guarda.")
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
# Encabezado
# ---------------------------------------------------------------------------
st.markdown('<div class="eu-marca">Euthetos</div>'
            '<div class="eu-lema">Las convocatorias del Estado peruano a las que puedes postular, en un minuto.</div>',
            unsafe_allow_html=True)
if aviso_cv:
    st.warning(aviso_cv)

if not carrera.strip():
    st.markdown(f"""
<div class="eu-pasos">
  <div class="eu-paso"><i>PASO 1</i><b>Escribe tu carrera</b>
    <span>En el panel de la izquierda. Sirve cualquier carrera universitaria o técnica.</span></div>
  <div class="eu-paso"><i>PASO 2</i><b>Adjunta tu currículo</b>
    <span>Se leen tu grado y tus periodos de trabajo. Tú confirmas cuáles cuentan.</span></div>
  <div class="eu-paso"><i>PASO 3</i><b>Revisa tus convocatorias</b>
    <span>Cada oferta indica si cumples lo que pide y muestra el requisito tal como se publicó.</span></div>
</div>
<p class="eu-nota">Hoy hay {len(ofertas):,} ofertas vigentes de {ofertas['institucion'].nunique():,} entidades
públicas en {ofertas['departamento'].nunique()} departamentos. Fuente: Talento Perú (SERVIR), leído hasta el
{corte:%d/%m/%Y a las %H:%M}. <i>Euthetos</i> significa «apto» en griego antiguo.</p>
""", unsafe_allow_html=True)
    st.stop()

# ---------------------------------------------------------------------------
# Periodos de trabajo leídos del CV: la persona decide cuáles cuentan
# ---------------------------------------------------------------------------
periodos = st.session_state.get("periodos", [])
if periodos:
    st.markdown('<p class="eu-seccion">Tu experiencia, según tu currículo</p>', unsafe_allow_html=True)
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
    st.markdown('<p class="eu-nota">Desmarca los periodos que no puedas acreditar con una constancia o un '
                'certificado. Los periodos que se superponen se cuentan una sola vez.</p>', unsafe_allow_html=True)
    if st.session_state.get("suma_periodos") != suma:           # cambió la selección: se actualiza el perfil
        st.session_state["suma_periodos"] = suma
        st.session_state["exp_general"] = st.session_state["exp_especifica"] = suma
elif texto_cv and not aviso_cv:
    st.info("No se encontraron periodos de trabajo en tu currículo. Indica tus años de experiencia en el panel izquierdo.")

with zona_confirmar:
    st.divider()
    nivel = st.selectbox("Grado más alto", reglas.NIVELES, key="nivel")
    exp_general = st.number_input("Años de experiencia laboral", 0.0, 50.0, step=0.5, format="%.1f", key="exp_general")
    exp_especifica = st.number_input("De ellos, en tu especialidad", 0.0, 50.0, step=0.5, format="%.1f", key="exp_especifica")
    colegiado = st.checkbox("Colegiatura y habilitación vigentes", key="colegiado")
    st.caption(f"{len(ofertas):,} ofertas vigentes. Talento Perú (SERVIR), leído hasta el {corte:%d/%m/%Y %H:%M}.")

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
por_cerrar = int((pd.concat([verdes, amarillas])["dias"] <= 3).sum())
st.markdown(f"""
<div class="eu-resumen">
  <div class="eu-dato" style="--c:#2E7D5B"><b>{len(verdes):,}</b><span>Cumples lo medible</span></div>
  <div class="eu-dato" style="--c:#C28A1E"><b>{len(amarillas):,}</b><span>Conviene revisar</span></div>
  <div class="eu-dato" style="--c:#B0564C"><b>{len(rojas):,}</b><span>Te falta algún requisito</span></div>
  <div class="eu-dato" style="--c:#1F4E5F"><b>{por_cerrar:,}</b><span>Cierran en 3 días o menos</span></div>
</div>""", unsafe_allow_html=True)


def nivel_de_afinidad(puesto):
    return "muy alta" if puesto <= 0.05 else "alta" if puesto <= 0.20 else "media" if puesto <= 0.50 else "baja"


def tarjeta(oferta):
    """Una oferta: puesto, entidad, datos clave, motivos y, plegado, el texto de la entidad."""
    sueldo = f"S/ {oferta['remuneracion_soles']:,.0f}" if oferta["remuneracion_soles"] == oferta["remuneracion_soles"] else "Sueldo sin dato"
    cierre = "Cierra hoy" if oferta["dias"] == 0 else "Cierra mañana" if oferta["dias"] == 1 else f"Cierra en {oferta['dias']} días"
    chips = [f"<span>{sueldo}</span>",
             f'<span class="{"urgente" if oferta["dias"] <= 3 else ""}">{cierre}</span>',
             f"<span>{html.escape(legible(oferta['ubicacion'], True))}</span>",
             f"<span>{html.escape(oferta['regimen'])}</span>"]
    if afinidad is not None:
        referencia = "currículo" if texto_cv else "carrera"
        chips.append(f"<span>Afinidad con tu {referencia}: {nivel_de_afinidad(oferta['puesto_afinidad'])}</span>")
    filas = "".join(f'<div class="eu-motivo"><span class="eu-estado {estado}">{ETIQUETAS[estado]}</span>'
                    f"<span>{html.escape(texto)}</span></div>" for estado, texto in oferta["motivos"])
    with st.container(border=True, key=f"oferta_{oferta['id']}_{oferta['color']}"):
        st.markdown(f'<div class="eu-titulo">{html.escape(legible(oferta["titulo"]))}</div>'
                    f'<div class="eu-entidad">{html.escape(legible(oferta["institucion"], True))}</div>'
                    f'<div class="eu-chips">{"".join(chips)}</div>{filas}', unsafe_allow_html=True)
        with st.expander("Requisitos publicados por la entidad"):
            secciones = [("Formación", "formacion"), ("Experiencia", "experiencia"),
                         ("Especialización", "especializacion"), ("Conocimientos", "conocimientos")]
            st.markdown("".join(f'<p class="eu-literal"><b>{nombre}.</b> {html.escape(en_oraciones(oferta[campo]))}</p>'
                                for nombre, campo in secciones if isinstance(oferta[campo], str))
                        + f'<p class="eu-nota">Convocatoria {html.escape(str(oferta["numero_convocatoria"]))} · '
                          f'Aviso N.° {html.escape(str(oferta["id"]))} · {oferta["vacantes"]} vacante(s) · '
                          f'Publicada del {pd.Timestamp(oferta["fecha_inicio"]):%d/%m/%Y} al {pd.Timestamp(oferta["fecha_fin"]):%d/%m/%Y}. '
                          "El texto se muestra en minúsculas para facilitar la lectura.</p>", unsafe_allow_html=True)
            botones = st.columns([2, 2, 5])
            if isinstance(oferta["enlace_bases"], str):
                botones[0].link_button("Bases de la entidad", oferta["enlace_bases"], use_container_width=True)
            botones[1].link_button("Abrir Talento Perú", URL_TALENTO, use_container_width=True)


def mostrar(grupo, explicacion, vacio):
    """Lista de ofertas de un color: primero las que nombran la carrera y, dentro de ellas,
    de la más parecida al CV a la menos parecida."""
    st.markdown(f'<p class="eu-nota">{explicacion}</p>', unsafe_allow_html=True)
    if grupo.empty:
        st.write(vacio)
        return
    grupo = grupo.sort_values(["menciona_carrera", "afinidad", "dias"], ascending=[False, False, True])
    if len(grupo) > MAX_POR_PESTANA:
        st.markdown(f'<p class="eu-nota">Se muestran las {MAX_POR_PESTANA} más idóneas de {len(grupo):,}: primero '
                    "las que nombran tu carrera y, entre ellas, las más parecidas a tu currículo.</p>",
                    unsafe_allow_html=True)
    for oferta in grupo.head(MAX_POR_PESTANA).to_dict("records"):
        tarjeta(oferta)


pestana_verde, pestana_amarilla, pestana_roja = st.tabs([
    f"Cumples lo medible ({len(verdes):,})", f"Conviene revisar ({len(amarillas):,})",
    f"Te falta algún requisito ({len(rojas):,})"])
with pestana_verde:
    mostrar(verdes, "Cumples la carrera, el grado y los años de experiencia que se pudieron medir.",
            "Ninguna oferta cumple todo lo medible con este perfil. Mira la pestaña «Conviene revisar».")
with pestana_amarilla:
    mostrar(amarillas, "Nada te descarta, pero hay algo que debes leer tú: carreras afines, colegiatura, "
                       "posgrado o un texto poco claro.", "No hay ofertas por revisar.")
with pestana_roja:
    mostrar(rojas, "Te falta al menos un requisito medible. Sirve para saber qué te separa de cada puesto.",
            "No hay ofertas en esta categoría.")

descarga = pd.concat([verdes, amarillas]).sort_values(["menciona_carrera", "afinidad"], ascending=False)
st.download_button("Descargar mis convocatorias (CSV)",
                   descarga[["color", "titulo", "institucion", "ubicacion", "regimen", "remuneracion", "fecha_fin",
                             "formacion", "experiencia", "numero_convocatoria", "id", "enlace_bases"]]
                   .to_csv(index=False).encode("utf-8-sig"),
                   file_name="mis_convocatorias_euthetos.csv", mime="text/csv")

st.markdown(
    '<p class="eu-nota" style="margin-top:2rem">Euthetos compara solo lo medible (carrera, grado y años de '
    "experiencia) y muestra cada requisito tal como lo publicó la entidad. Quien decide si una persona es apta es "
    "el comité de selección: lee siempre las bases antes de postular. Fuente de los datos: Talento Perú (SERVIR), "
    "portal oficial de ofertas laborales del Estado.</p>", unsafe_allow_html=True)
