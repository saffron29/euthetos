# Euthetos

> *Euthetos* (εὔθετος): «apto», «bien dispuesto para algo», en griego antiguo.

Euthetos le dice a cualquier profesional, en un minuto, a qué convocatorias laborales del Estado
peruano puede postular: la persona escribe su carrera y adjunta su CV, y la aplicación compara su
perfil con todas las ofertas vigentes de Talento Perú (SERVIR), mostrando el texto literal de cada
requisito.

**Estado:** en construcción (proyecto final de la Diplomatura Q-Lab PUCP). El README completo se
publica junto con la primera versión desplegada.

## Cómo correrlo

```bash
python -m venv .venv
.venv\Scripts\activate            # en Windows
pip install -r requirements.txt
streamlit run app.py
```

Para actualizar los datos:

```bash
python ingesta.py                 # lee las ofertas vigentes de Talento Perú (varias horas)
python emparejar.py               # calcula los vectores de las ofertas
```
