"""
Euthetos («apto», en griego antiguo)
Descubre en un minuto a qué convocatorias del Estado peruano puedes postular.

    streamlit run app.py

La persona escribe su carrera y adjunta su CV. La aplicación:
  1. lee el CV y propone grado y años de experiencia (la persona los confirma);
  2. compara ese perfil con cada oferta vigente de Talento Perú (reglas.py);
  3. ordena las ofertas por parecido con el CV (emparejar.py).
"""

import hashlib
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

import cv
import emparejar
import reglas

CARPETA = Path(__file__).parent / "datos"
URL_TALENTO = "https://app.servir.gob.pe/DifusionOfertasExterno/faces/consultas/ofertas_laborales.xhtml"
CV_DE_EJEMPLO = {
    "Enfermería (Lucía, licenciada)": ("enfermeria.txt", "Enfermería"),
    "Ingeniería Civil (Diego, bachiller)": ("ingenieria_civil.txt", "Ingeniería Civil"),
    "Derecho (Valeria, abogada)": ("derecho.txt", "Derecho"),
}
MAX_POR_PESTANA = 25
ICONOS = {"ok": "✅", "revisar": "⚠️", "falta": "❌"}

st.set_page_config(page_title="Euthetos · empleo público", page_icon="🎯", layout="wide")


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


@st.cache_data(show_spinner="Buscando las ofertas más parecidas a tu CV…")
def calcular_afinidad(carrera, texto_cv, ids):
    E = vectores_alineados(ids)
    if E is None:
        return None
    q = emparejar.vector_de_cv(cargar_modelo(), carrera, texto_cv)
    return emparejar.afinidad(E, q)


# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
hoy = datetime.now(ZoneInfo("America/Lima")).date().isoformat()
ofertas = cargar_ofertas(hoy)
corte = pd.to_datetime(ofertas["leido"]).max()

st.title("🎯 Euthetos")
st.markdown("**¿A qué convocatorias del Estado puedes postular?** Escribe tu carrera, adjunta tu CV y "
            "míralo en un minuto. *Euthetos* significa «apto» en griego antiguo.")

# ---------------------------------------------------------------------------
# Paso 1: carrera y CV
# ---------------------------------------------------------------------------
st.subheader("1 · Tu carrera y tu CV")
columna_carrera, columna_cv, columna_ejemplo = st.columns([2, 3, 2])
# Un enlace como .../?demo=enfermeria abre la aplicación con ese CV ficticio ya cargado
demo = st.query_params.get("demo")
if demo and "ejemplo" not in st.session_state:
    coincidencias = [nombre for nombre, (archivo_cv, _) in CV_DE_EJEMPLO.items() if archivo_cv.startswith(demo)]
    if coincidencias:
        st.session_state["ejemplo"] = coincidencias[0]

with columna_ejemplo:
    ejemplo = st.selectbox("¿No tienes tu CV a la mano? Prueba con uno ficticio",
                           ["—"] + list(CV_DE_EJEMPLO), key="ejemplo")
with columna_cv:
    archivo = st.file_uploader("Adjunta tu CV (PDF, Word o texto)", type=["pdf", "docx", "txt"])
    st.caption("🔒 Tu CV se lee en el momento y no se guarda.")

texto_cv, carrera_sugerida = "", None
if archivo is not None:
    try:
        texto_cv = cv.leer_cv(archivo.name, archivo.getvalue())
    except Exception:
        st.error("No se pudo leer ese archivo. Prueba con otro formato (PDF con texto, .docx o .txt).")
    if archivo.name.lower().endswith(".pdf") and len(texto_cv.strip()) < 200 and texto_cv is not None:
        st.warning("Este PDF parece escaneado (no tiene texto). Súbelo en Word o como PDF con texto.")
elif ejemplo != "—":
    nombre_archivo, carrera_sugerida = CV_DE_EJEMPLO[ejemplo]
    texto_cv = (CARPETA / "cv_ejemplo" / nombre_archivo).read_text(encoding="utf-8")

# Cuando llega un CV nuevo, se proponen el grado y la experiencia leídos de él
huella = hashlib.sha1(texto_cv.encode("utf-8")).hexdigest()
if st.session_state.get("huella_cv") != huella:
    st.session_state["huella_cv"] = huella
    estimado = cv.estimar_perfil(texto_cv) if texto_cv else {"nivel": None, "colegiado": False, "anios_experiencia": None}
    st.session_state["nivel"] = reglas.NIVELES[estimado["nivel"] if estimado["nivel"] is not None else reglas.BACHILLER]
    st.session_state["exp_general"] = float(estimado["anios_experiencia"] or 0)
    st.session_state["exp_especifica"] = float(estimado["anios_experiencia"] or 0)
    st.session_state["colegiado"] = estimado["colegiado"]
    st.session_state["cv_estimado"] = estimado
    if carrera_sugerida:
        st.session_state["carrera"] = carrera_sugerida

with columna_carrera:
    carrera = st.text_input("Tu carrera", key="carrera", placeholder="Ej.: Contabilidad, Psicología, Enfermería…")

if not carrera.strip():
    st.info("Escribe tu carrera para empezar. Hoy hay "
            f"**{len(ofertas):,} ofertas vigentes** de {ofertas['institucion'].nunique():,} entidades públicas.")
    st.stop()

# ---------------------------------------------------------------------------
# Paso 2: confirmar lo leído del CV
# ---------------------------------------------------------------------------
st.subheader("2 · Confirma tu perfil")
estimado = st.session_state.get("cv_estimado", {})
if texto_cv and estimado.get("anios_experiencia") is not None:
    st.caption("Esto es lo que se leyó de tu CV. **Corrígelo si hace falta**: es una estimación.")
elif texto_cv:
    st.caption("No se pudieron leer los periodos de trabajo de tu CV: **indica tus años de experiencia**.")
else:
    st.caption("Sin CV, la búsqueda usa solo tu carrera y lo que indiques aquí.")

c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
nivel = c1.selectbox("Tu grado más alto", reglas.NIVELES, key="nivel")
exp_general = c2.number_input("Años de experiencia laboral (total)", 0.0, 50.0, step=0.5, key="exp_general")
exp_especifica = c3.number_input("…de ellos, en tu especialidad", 0.0, 50.0, step=0.5, key="exp_especifica")
colegiado = c4.checkbox("Tengo colegiatura y habilitación vigentes", key="colegiado")

perfil = {"carrera": carrera.strip(), "nivel": reglas.NIVELES.index(nivel), "colegiado": colegiado,
          "exp_general": exp_general, "exp_especifica": min(exp_especifica, exp_general)}

# ---------------------------------------------------------------------------
# Paso 3: resultados
# ---------------------------------------------------------------------------
colores, motivos, estado_carrera = evaluar(tuple(sorted(perfil.items())), hoy)
tabla = ofertas.assign(color=colores, motivos=motivos, estado_carrera=estado_carrera)
tabla["menciona_carrera"] = tabla["estado_carrera"] == "si"

afinidad = calcular_afinidad(perfil["carrera"], texto_cv, tuple(ofertas["id"]))
if afinidad is None:
    tabla["afinidad"] = 0.0
    st.info("Aún no se calcularon los vectores de las ofertas: los resultados se ordenan por fecha de cierre.")
else:
    tabla["afinidad"] = afinidad
# La similitud no tiene una escala fija: lo que importa es el orden entre ofertas
tabla["puesto_afinidad"] = tabla["afinidad"].rank(ascending=False, pct=True)

st.subheader("3 · Tus convocatorias")
f1, f2, f3, f4 = st.columns([3, 2, 2, 2])
departamentos = f1.multiselect("Departamento", sorted(tabla["departamento"].unique()), placeholder="Todo el Perú")
sueldo_minimo = f2.number_input("Remuneración mínima (S/)", 0, 20000, 0, step=500)
solo_afines = f3.toggle("Solo las más parecidas a mi CV", value=False,
                        help="Muestra únicamente el 20% de ofertas con mayor parecido a tu CV.")

sin_carrera = f4.toggle("Incluir puestos que no piden carrera", value=perfil["nivel"] <= reglas.TECNICO,
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
m1, m2, m3, m4 = st.columns(4)
m1.metric("Ofertas vigentes analizadas", f"{len(vista):,}")
m2.metric("🟢 Encajas en lo medible", f"{len(verdes):,}")
m3.metric("🟡 Vale la pena revisar", f"{len(amarillas):,}")
m4.metric("⏳ Cierran en 3 días o menos", f"{int((pd.concat([verdes, amarillas])['dias'] <= 3).sum()):,}",
          help="Entre las verdes y las amarillas.")


def etiqueta_afinidad(puesto):
    if afinidad is None:
        return ""
    return "muy alto" if puesto <= 0.05 else "alto" if puesto <= 0.20 else "medio" if puesto <= 0.50 else "bajo"


def mostrar(grupo, vacio):
    """Lista de ofertas de un color: primero las que nombran la carrera y, dentro de ellas,
    de la más parecida al CV a la menos parecida."""
    if grupo.empty:
        st.write(vacio)
        return
    grupo = grupo.sort_values(["menciona_carrera", "afinidad", "dias"], ascending=[False, False, True])
    if len(grupo) > MAX_POR_PESTANA:
        st.caption(f"Se muestran las {MAX_POR_PESTANA} más idóneas de {len(grupo):,}: primero las que nombran "
                   "tu carrera y, entre ellas, las más parecidas a tu CV.")
    for oferta in grupo.head(MAX_POR_PESTANA).to_dict("records"):
        sueldo = f"S/ {oferta['remuneracion_soles']:,.0f}" if oferta["remuneracion_soles"] == oferta["remuneracion_soles"] else "sin dato"
        cierre = "cierra hoy" if oferta["dias"] == 0 else f"cierra en {oferta['dias']} días"
        with st.expander(f"**{oferta['titulo']}** · {oferta['institucion']} — {sueldo} · {cierre}"):
            izquierda, derecha = st.columns(2)
            with izquierda:
                st.markdown("**Por qué**")
                for estado, texto in oferta["motivos"]:
                    st.markdown(f"{ICONOS[estado]} {texto}")
                if afinidad is not None:
                    st.markdown(f"🧭 Parecido con tu CV: **{etiqueta_afinidad(oferta['puesto_afinidad'])}**")
                st.markdown(f"📍 {oferta['ubicacion']} · {oferta['regimen']} · {oferta['vacantes']} vacante(s)  \n"
                            f"📅 Publicada del {oferta['fecha_inicio']} al {oferta['fecha_fin']}")
            with derecha:
                st.markdown("**Texto literal de la oferta**")
                for nombre in ("formacion", "experiencia", "especializacion", "conocimientos"):
                    if isinstance(oferta[nombre], str):
                        st.markdown(f"*{nombre.capitalize()}:* {oferta[nombre]}")
            st.markdown(f"N.° de convocatoria: `{oferta['numero_convocatoria']}` · N.° de aviso en Talento Perú: `{oferta['id']}`")
            enlaces = st.columns(4)
            if isinstance(oferta["enlace_bases"], str):
                enlaces[0].link_button("Bases o página de la entidad", oferta["enlace_bases"])
            enlaces[1].link_button("Buscar en Talento Perú", URL_TALENTO)


pestana_verde, pestana_amarilla, pestana_roja = st.tabs([
    f"🟢 Encajas ({len(verdes):,})", f"🟡 Revisar ({len(amarillas):,})", f"🔴 No encajas ({len(rojas):,})"])
with pestana_verde:
    st.caption("Cumples la carrera, el grado y los años de experiencia que se pudieron medir.")
    mostrar(verdes, "Ninguna oferta cumple todo lo medible con este perfil. Mira la pestaña 🟡.")
with pestana_amarilla:
    st.caption("Nada te descarta, pero hay algo que debes leer tú: carreras afines, colegiatura, posgrado o un texto poco claro.")
    mostrar(amarillas, "No hay ofertas por revisar.")
with pestana_roja:
    st.caption("Te falta al menos un requisito medible. Sirve para saber qué te separa de cada puesto.")
    mostrar(rojas, "No hay ofertas en esta categoría.")

descarga = pd.concat([verdes, amarillas]).sort_values(["menciona_carrera", "afinidad"], ascending=False)
st.download_button("⬇️ Descargar mis convocatorias (CSV)",
                   descarga[["color", "titulo", "institucion", "ubicacion", "regimen", "remuneracion", "fecha_fin",
                             "formacion", "experiencia", "numero_convocatoria", "id", "enlace_bases"]]
                   .to_csv(index=False).encode("utf-8-sig"),
                   file_name="mis_convocatorias_euthetos.csv", mime="text/csv")

st.divider()
st.caption(
    f"Fuente: Talento Perú (SERVIR), portal oficial de ofertas laborales del Estado. Datos leídos hasta el "
    f"{corte:%d/%m/%Y %H:%M}. · Euthetos compara solo lo medible (carrera, grado y años de experiencia) y muestra "
    "el texto literal de cada requisito: quien decide si una persona es apta es el comité de selección de cada "
    "entidad. Lee siempre las bases antes de postular."
)
