"""
Ingesta: lee las ofertas laborales vigentes del Estado peruano en Talento Perú (SERVIR)
https://app.servir.gob.pe/DifusionOfertasExterno/faces/consultas/ofertas_laborales.xhtml

Cómo funciona la página (comprobado el 10/11/2026):
  - Los datos vienen en el HTML: basta requests + BeautifulSoup, sin Selenium.
  - Es una aplicación JSF: buscar, pasar de página y abrir el detalle se hacen
    ENVIANDO EL FORMULARIO (POST) con un código llamado ViewState, que el
    servidor renueva en cada respuesta. Por eso se usa una sesión de requests.
  - La lista muestra 10 ofertas por página, de todos los regímenes (CAS, 728,
    276, Ley 30057, prácticas...). El detalle trae Formación, Experiencia,
    Especialización y Conocimientos.

Uso:
    python ingesta.py                 # recorre todas las páginas (varias horas)
    python ingesta.py --paginas 2     # prueba corta
    python ingesta.py --exportar      # solo arma datos/convocatorias.csv con lo ya leído

Cada oferta leída se guarda de inmediato en datos/crudo/avisos.jsonl, de modo
que si la lectura se corta, se retoma sin volver a pedir lo ya leído.
"""

import argparse
import hashlib
import json
import re
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

URL_LISTADO = "https://app.servir.gob.pe/DifusionOfertasExterno/faces/consultas/ofertas_laborales.xhtml"
FORMULARIO = "frmLstOfertsLabo"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/155.0 Safari/537.36"),
    "Accept-Language": "es-PE,es;q=0.9",
}
CABECERAS_AJAX = {"Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest"}

PAUSA_SEGUNDOS = 2          # entre pedido y pedido: cortesía con el servidor
PAUSA_CORTA = 0.7           # al pasar páginas ya leídas
TIMEOUT = 40
MAX_REINTENTOS = 5          # veces que se reabre la sesión si se corta

CARPETA = Path(__file__).parent / "datos"
RUTA_CRUDO = CARPETA / "crudo" / "avisos.jsonl"
RUTA_CSV = CARPETA / "convocatorias.csv"


class BloqueoError(Exception):
    """El sitio respondió algo inesperado: conviene detenerse, no insistir."""


# ---------------------------------------------------------------------------
# Texto y fechas
# ---------------------------------------------------------------------------
def limpiar(texto):
    """Quita espacios repetidos, saltos de línea y tabulaciones."""
    if texto is None:
        return None
    texto = re.sub(r"\s+", " ", str(texto)).strip()
    return texto or None


def normalizar(texto):
    """Minúsculas y sin tildes: 'Formación' -> 'formacion'."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFD", str(texto).lower())
    texto = "".join(letra for letra in texto if unicodedata.category(letra) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


def fecha_numerica(texto):
    """'05/11/2026' -> '2026-11-05'."""
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", texto or "")
    if not m:
        return None
    dia, mes, anio = map(int, m.groups())
    try:
        return date(anio, mes, dia).isoformat()
    except ValueError:
        return None


def monto_en_soles(texto):
    """'S/. 3,700.00' -> 3700.0"""
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)", texto or "")
    return float(m.group(1).replace(",", "")) if m else None


# ---------------------------------------------------------------------------
# El formulario
# ---------------------------------------------------------------------------
def botones_por_texto(soup):
    """{'Buscar': 'frmLstOfertsLabo:j_idt46', 'Sig.': ...}.

    Los id (j_idt46...) los genera el servidor y pueden cambiar; el texto del
    botón no cambia: por eso se busca por contenido.
    """
    botones = {}
    for boton in soup.find_all("button"):
        texto, identificador = limpiar(boton.get_text()), boton.get("id")
        if texto and identificador and texto not in botones:
            botones[texto] = identificador
    return botones


def abrir_formulario(sesion):
    """Primera visita: guarda los campos del formulario y el ViewState."""
    respuesta = sesion.get(URL_LISTADO, timeout=TIMEOUT)
    respuesta.raise_for_status()
    soup = BeautifulSoup(respuesta.text, "lxml")
    formulario = soup.find("form", id=FORMULARIO)
    if formulario is None:
        raise BloqueoError("SERVIR no devolvió el formulario de búsqueda")

    campos = {}
    for entrada in formulario.find_all("input"):
        nombre = entrada.get("name")
        if nombre and "idPnlRepeatPuestos" not in nombre:      # no los botones de cada aviso
            campos[nombre] = entrada.get("value", "")
    campos[f"{FORMULARIO}:cboDep_input"] = "0"                   # todo el país
    campos[f"{FORMULARIO}:txtPerfil"] = ""                       # sin filtro: todas las carreras
    return campos, botones_por_texto(formulario)


def enviar(sesion, campos, boton):
    """Aprieta un botón (Buscar, Sig.) y devuelve la lista actualizada."""
    datos = dict(campos)
    datos.update({
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": boton,
        "javax.faces.partial.execute": "@all",
        "javax.faces.partial.render": f"{FORMULARIO}:mensaje {FORMULARIO}",
        boton: boton,
    })
    respuesta = sesion.post(URL_LISTADO, data=datos, headers=CABECERAS_AJAX, timeout=TIMEOUT)
    respuesta.raise_for_status()
    if "incident id" in respuesta.text.lower():
        raise BloqueoError("SERVIR bloqueó el pedido")

    # El servidor manda un ViewState nuevo: se usa en el siguiente pedido
    nuevo = re.search(r'javax\.faces\.ViewState[^"]*"><!\[CDATA\[(.*?)\]\]>', respuesta.text)
    if nuevo:
        campos["javax.faces.ViewState"] = nuevo.group(1)

    # La respuesta es XML; el HTML de la lista viene dentro de un bloque CDATA
    html = re.search(r'<update id="%s"><!\[CDATA\[(.*?)\]\]></update>' % FORMULARIO,
                     respuesta.text, re.S)
    if not html:
        raise BloqueoError("SERVIR respondió sin la lista de ofertas")
    return BeautifulSoup(html.group(1), "lxml")


# ---------------------------------------------------------------------------
# Leer la lista y el detalle
# ---------------------------------------------------------------------------
def _valor(datos, etiqueta):
    """Busca un dato por el comienzo de su etiqueta: 'fecha fin' -> 'Fecha Fin de Publicación:'."""
    for clave, valor in datos.items():
        if clave.startswith(etiqueta):
            return valor
    return None


def leer_tarjetas(soup):
    """Convierte cada recuadro de la lista en un diccionario."""
    tarjetas = []
    for cuadro in soup.select("div.cuadro-vacantes"):
        datos = {}
        for etiqueta in cuadro.select("span.sub-titulo"):
            valor = etiqueta.find_next_sibling("span")
            datos[normalizar(etiqueta.get_text())] = limpiar(valor.get_text(" ")) if valor else None
        titulo = cuadro.select_one("div.titulo-vacante")
        entidad = cuadro.select_one("div.nombre-entidad")
        boton = cuadro.find("button", title=re.compile("Ver m"))
        tarjetas.append({
            "titulo": limpiar(titulo.get_text(" ")) if titulo else None,
            "institucion": limpiar(entidad.get_text(" ")) if entidad else None,
            "ubicacion": _valor(datos, "ubicacion"),
            "numero_convocatoria": _valor(datos, "numero de convocatoria"),
            "vacantes": _valor(datos, "cantidad de vacantes"),
            "remuneracion": _valor(datos, "remuneracion"),
            "fecha_inicio": fecha_numerica(_valor(datos, "fecha inicio")),
            "fecha_fin": fecha_numerica(_valor(datos, "fecha fin")),
            "boton_detalle": boton.get("id") if boton else None,
        })
    return tarjetas


def leer_detalle(sesion, campos, boton_detalle):
    """Aprieta '¡Ver más!' y lee las secciones del aviso (formación, experiencia...)."""
    datos = dict(campos)
    datos[boton_detalle] = ""
    respuesta = sesion.post(URL_LISTADO, data=datos, timeout=TIMEOUT)
    respuesta.raise_for_status()
    if "incident id" in respuesta.text.lower():
        raise BloqueoError("SERVIR bloqueó el pedido")
    soup = BeautifulSoup(respuesta.text, "lxml")

    secciones = {}
    for etiqueta in soup.select(".sub-titulo-2, .sub-titulo"):
        valor = etiqueta.find_next_sibling("span", class_="detalle-sp")
        if valor:
            secciones.setdefault(normalizar(etiqueta.get_text()).rstrip(":"), limpiar(valor.get_text(" ")))
    if not secciones:
        raise BloqueoError("El detalle llegó vacío (¿se venció la sesión?)")

    # DETALLE: lo que sigue a la etiqueta hasta la próxima etiqueta (texto o enlace a las bases)
    detalle_texto, enlaces = [], []
    etiqueta = soup.find(lambda t: t.name in ("span", "p") and normalizar(t.get_text()) == "detalle:")
    if etiqueta:
        for hermano in etiqueta.next_siblings:
            if getattr(hermano, "get", None) and "sub-titulo" in (hermano.get("class") or []):
                break
            texto = hermano.get_text(" ") if hasattr(hermano, "get_text") else str(hermano)
            detalle_texto.append(texto)
            if hasattr(hermano, "find_all"):
                enlaces += [a["href"] for a in ([hermano] if hermano.name == "a" else hermano.find_all("a"))
                            if a.get("href")]
    detalle_texto = limpiar(" ".join(detalle_texto))
    # Algunas entidades escriben texto o "#" en el campo del enlace: solo valen direcciones web
    enlaces = [e.strip() for e in enlaces if re.match(r"\s*(https?://|www\.)", e)]
    if not enlaces and detalle_texto:
        enlaces = re.findall(r"https?://\S+", detalle_texto)
    enlaces = [e if e.startswith("http") else "https://" + e for e in enlaces]

    # El N.° de aviso tiene 6 cifras; con 5 se confundía con leyes citadas en el texto ("Ley N° 23536")
    numero = re.search(r"N°\s*(\d{6,})", soup.get_text(" "))
    return {
        "n_aviso": numero.group(1) if numero else None,
        "formacion": _valor(secciones, "formacion"),
        "experiencia": _valor(secciones, "experiencia"),
        "especializacion": _valor(secciones, "especializacion"),
        "conocimientos": _valor(secciones, "conocimiento"),
        "detalle": detalle_texto,
        "enlace_bases": enlaces[0] if enlaces else None,
        "secciones": secciones,
    }


def clave_de(tarjeta):
    """Un código estable para reconocer el aviso aunque cambie de página."""
    partes = [str(tarjeta.get(c)) for c in ("institucion", "titulo", "numero_convocatoria", "ubicacion",
                                             "remuneracion", "vacantes", "fecha_inicio", "fecha_fin")]
    return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Recorrido completo
# ---------------------------------------------------------------------------
def claves_ya_leidas():
    if not RUTA_CRUDO.exists():
        return set()
    with open(RUTA_CRUDO, encoding="utf-8") as archivo:
        return {json.loads(linea)["clave"] for linea in archivo if linea.strip()}


def guardar(aviso):
    RUTA_CRUDO.parent.mkdir(parents=True, exist_ok=True)
    with open(RUTA_CRUDO, "a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(aviso, ensure_ascii=False) + "\n")


def ir_a_pagina(sesion, campos, botones, pagina):
    """Abre la lista sin filtro y avanza con 'Sig.' hasta la página pedida."""
    soup = enviar(sesion, campos, botones["Buscar"])
    for _ in range(pagina - 1):
        time.sleep(PAUSA_CORTA)
        soup = enviar(sesion, campos, botones_por_texto(soup).get("Sig.", botones["Sig."]))
    return soup


def recorrer(max_paginas=None):
    """Lee la lista página por página y el detalle de cada oferta nueva."""
    leidas = claves_ya_leidas()
    print(f"Ya leídas de antes: {len(leidas)}", flush=True)
    pagina, total_paginas, reintentos, nuevas = 1, None, 0, 0
    sesion = campos = botones = soup = None

    while total_paginas is None or pagina <= total_paginas:
        try:
            if soup is None:                                    # primera vez o sesión reabierta
                sesion = requests.Session()
                sesion.headers.update(HEADERS)
                campos, botones = abrir_formulario(sesion)
                time.sleep(PAUSA_SEGUNDOS)
                soup = ir_a_pagina(sesion, campos, botones, pagina)
                paginacion = re.search(r"Página\s+\d+\s+de\s+(\d+)", soup.get_text(" "))
                total_paginas = int(paginacion.group(1)) if paginacion else pagina
                if max_paginas:
                    total_paginas = min(total_paginas, max_paginas)

            tarjetas = leer_tarjetas(soup)
            antes = nuevas
            for tarjeta in tarjetas:
                clave = clave_de(tarjeta)
                if clave in leidas or not tarjeta["boton_detalle"]:
                    continue
                time.sleep(PAUSA_SEGUNDOS)
                detalle = leer_detalle(sesion, campos, tarjeta["boton_detalle"])
                aviso = {"clave": clave, "leido": datetime.now().isoformat(timespec="seconds"),
                         **{c: v for c, v in tarjeta.items() if c != "boton_detalle"}, **detalle}
                guardar(aviso)
                leidas.add(clave)
                nuevas += 1

            if pagina % 5 == 0 or pagina == total_paginas:
                print(f"{datetime.now():%H:%M:%S} · página {pagina} de {total_paginas} · "
                      f"{nuevas} ofertas nuevas · {len(leidas)} en total", flush=True)
            pagina += 1
            reintentos = 0
            if pagina <= total_paginas:
                # si toda la página ya estaba leída, se pasa más rápido
                time.sleep(PAUSA_SEGUNDOS if nuevas > antes else PAUSA_CORTA)
                soup = enviar(sesion, campos, botones_por_texto(soup).get("Sig.", botones["Sig."]))

        except (BloqueoError, requests.RequestException) as error:
            reintentos += 1
            print(f"{datetime.now():%H:%M:%S} · corte en la página {pagina}: {type(error).__name__}: {error} "
                  f"(reintento {reintentos} de {MAX_REINTENTOS})", flush=True)
            if reintentos > MAX_REINTENTOS:
                print("Demasiados cortes seguidos: se conserva lo leído y se detiene.", flush=True)
                break
            time.sleep(30 * reintentos)                         # esperar más cada vez, sin insistir
            soup = None                                         # reabrir la sesión y volver a la página

    print(f"Fin del recorrido: {nuevas} ofertas nuevas, {len(leidas)} en total.", flush=True)


# ---------------------------------------------------------------------------
# De lo leído al CSV que usa la aplicación
# ---------------------------------------------------------------------------
COLUMNAS = ["id", "n_aviso", "titulo", "institucion", "ubicacion", "numero_convocatoria", "vacantes",
            "remuneracion", "remuneracion_soles", "fecha_inicio", "fecha_fin",
            "formacion", "experiencia", "especializacion", "conocimientos",
            "detalle", "enlace_bases", "leido"]


def exportar_csv(hoy=None):
    """Arma datos/convocatorias.csv solo con las ofertas que siguen vigentes."""
    hoy = hoy or date.today().isoformat()
    with open(RUTA_CRUDO, encoding="utf-8") as archivo:
        avisos = [json.loads(linea) for linea in archivo if linea.strip()]
    df = pd.DataFrame(avisos).drop_duplicates("clave", keep="last")
    # El identificador es la clave de la tarjeta: el N.° de aviso se repite en algunas ofertas
    df["id"] = df["clave"]
    df["n_aviso"] = df["n_aviso"].where(df["n_aviso"].fillna("").str.len() >= 6)
    df["remuneracion_soles"] = df["remuneracion"].map(monto_en_soles)
    vigentes = df[df["fecha_fin"].fillna("9999") >= hoy]
    vigentes = vigentes.sort_values(["fecha_fin", "institucion", "titulo"])[COLUMNAS]
    vigentes.to_csv(RUTA_CSV, index=False, encoding="utf-8")
    print(f"{RUTA_CSV.name}: {len(vigentes)} ofertas vigentes al {hoy} (de {len(df)} leídas)")
    return vigentes


if __name__ == "__main__":
    opciones = argparse.ArgumentParser(description="Lee las ofertas vigentes de Talento Perú (SERVIR)")
    opciones.add_argument("--paginas", type=int, help="leer solo las primeras N páginas (prueba)")
    opciones.add_argument("--exportar", action="store_true", help="solo armar el CSV con lo ya leído")
    argumentos = opciones.parse_args()
    if not argumentos.exportar:
        recorrer(argumentos.paginas)
    exportar_csv()
