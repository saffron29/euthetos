"""
Búsqueda por significado: ordena las ofertas según cuánto se parecen al CV.

Es la «R» de RAG vista en la Sesión 08 del curso (llms_a_prueba.ipynb):
embeddings + producto punto. Se usa el mismo modelo abierto de la clase,
`multilingual-e5-small`, que corre en CPU, sin clave y sin costo.

    python emparejar.py      # calcula los vectores de datos/convocatorias.csv

Los vectores de las ofertas se calculan una sola vez y se guardan en
datos/embeddings.npz; en la aplicación solo se calcula el vector del CV.
"""

from pathlib import Path

import numpy as np
import pandas as pd

MODELO = "intfloat/multilingual-e5-small"
CARPETA = Path(__file__).parent / "datos"
RUTA_CSV = CARPETA / "convocatorias.csv"
RUTA_VECTORES = CARPETA / "embeddings.npz"
PALABRAS_POR_FRAGMENTO = 120
MAX_FRAGMENTOS = 12


def cargar_modelo():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODELO)


def texto_de_oferta(oferta):
    """Lo que se compara con el CV: el puesto y lo que pide."""
    partes = [("Puesto", oferta.get("titulo")), ("Formación", oferta.get("formacion")),
              ("Experiencia", oferta.get("experiencia")), ("Especialización", oferta.get("especializacion")),
              ("Conocimientos", oferta.get("conocimientos"))]
    return ". ".join(f"{nombre}: {valor}" for nombre, valor in partes if isinstance(valor, str) and valor)


def vectores_de_ofertas(embedder, ofertas):
    """Una fila por oferta, de largo 1: el producto punto ya es la similitud coseno."""
    docs = [texto_de_oferta(oferta) for oferta in ofertas.to_dict("records")]
    # e5 fue entrenado con prefijos: "passage:" para documentos, "query:" para preguntas
    return embedder.encode([f"passage: {d}" for d in docs], normalize_embeddings=True,
                           batch_size=32, show_progress_bar=True)


def trocear(texto):
    """Un CV no cabe entero en el modelo (512 tokens): se parte en fragmentos."""
    palabras = texto.split()
    fragmentos = [" ".join(palabras[i:i + PALABRAS_POR_FRAGMENTO])
                  for i in range(0, len(palabras), PALABRAS_POR_FRAGMENTO)]
    return fragmentos[:MAX_FRAGMENTOS]


def vector_de_cv(embedder, carrera, texto_cv):
    """El CV como un solo vector: el promedio de sus fragmentos, vuelto a largo 1."""
    fragmentos = trocear(texto_cv) or [carrera]
    V = embedder.encode([f"query: {carrera}. {f}" for f in fragmentos], normalize_embeddings=True)
    q = V.mean(axis=0)
    return q / np.linalg.norm(q)


def afinidad(E, q):
    """Similitud de cada oferta con el CV. Importa el orden, no el valor absoluto."""
    return E.astype(np.float32) @ q


def guardar_vectores(ids, E):
    np.savez_compressed(RUTA_VECTORES, ids=np.array(ids, dtype=str), E=E.astype(np.float16))


def cargar_vectores():
    """Devuelve {id: fila} y la matriz E, o (None, None) si aún no se calcularon."""
    if not RUTA_VECTORES.exists():
        return None, None
    archivo = np.load(RUTA_VECTORES)
    return {identificador: i for i, identificador in enumerate(archivo["ids"])}, archivo["E"]


if __name__ == "__main__":
    ofertas = pd.read_csv(RUTA_CSV, dtype=str)
    E = vectores_de_ofertas(cargar_modelo(), ofertas)
    guardar_vectores(ofertas["id"], E)
    print(f"matriz de embeddings: {E.shape} -> {RUTA_VECTORES.name}")
