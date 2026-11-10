"""Pruebas de las reglas con textos reales de Talento Perú (leídos el 10/11/2026)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import reglas
from reglas import BACHILLER, EGRESADO, SECUNDARIA, TECNICO, TITULO


def test_nivel_titulo_con_colegiatura():
    pedido = reglas.nivel_exigido("• TÍTULO PROFESIONAL EN DERECHO, COLEGIADO Y HABILITACIÓN VIGENTE")
    assert pedido["nivel"] == TITULO and pedido["pide_colegiatura"]


def test_nivel_bachiller():
    texto = "• GRADO DE BACHILLER UNIVERSITARIO EN LA CARRERA DE INGENIERÍA DE SISTEMAS, INGENIERÍA DE SOFTWARE"
    assert reglas.nivel_exigido(texto)["nivel"] == BACHILLER


def test_titulo_tecnico_no_es_titulo_profesional():
    assert reglas.nivel_exigido("• TÍTULO TÉCNICO EN ENFERMERÍA.")["nivel"] == TECNICO


def test_alternativas_vale_la_mas_baja():
    texto = ("TÍTULO TÉCNICO SUPERIOR EN ADMINISTRACIÓN, GESTIÓN DOCUMENTAL O EGRESADO(A) "
             "UNIVERSITARIO(A) DE LA CARRERA DE ADMINISTRACIÓN, ARCHIVÍSTICA O RECURSOS HUMANOS.")
    assert reglas.nivel_exigido(texto)["nivel"] == TECNICO


def test_secundaria():
    assert reglas.nivel_exigido("- ESTUDIOS SECUNDARIOS CONCLUIDOS.")["nivel"] == SECUNDARIA
    assert reglas.nivel_exigido("SECUNDARIA COMPLETA")["nivel"] == SECUNDARIA


def test_egresado_universitario():
    texto = "• EGRESADO/A UNIVERSITARIO/A EN LA CARRERA DE ADMINISTRACIÓN, DERECHO O INGENIERÍA INDUSTRIAL."
    assert reglas.nivel_exigido(texto)["nivel"] == EGRESADO


def test_maestria_se_avisa_aparte():
    texto = ("- TÍTULO UNIVERSIARIO EN CIENCIAS SOCIALES, ECONOMÍA, SOCIOLOGÍA, CIENCIA POLÍTICA. "
             "- CON MAESTRÍA (EGRESADO) EN GERENCIA SOCIAL")
    pedido = reglas.nivel_exigido(texto)
    assert pedido["pide_posgrado"] and pedido["nivel"] <= TITULO


def test_carrera_con_plural_y_tildes():
    texto = "TÍTULO UNIVERSITARIO EN CIENCIAS POLÍTICAS, SOCIOLOGÍA O ECONOMÍA"
    assert reglas.carrera_mencionada("Ciencia Política", texto) == "si"
    assert reglas.carrera_mencionada("Sociología", texto) == "si"
    assert reglas.carrera_mencionada("Enfermería", texto) == "no"


def test_carrera_por_sinonimo():
    assert reglas.carrera_mencionada("Derecho", "ABOGADO COLEGIADO Y HABILITADO") == "si"


def test_carreras_afines():
    texto = "• BACHILLER UNIVERSITARIO EN COMUNICACIÓN SOCIAL O PERIODISMO O AFINES."
    assert reglas.carrera_mencionada("Sociología", texto) == "afines"
    assert reglas.carrera_mencionada("Comunicaciones", texto) == "si"


def test_experiencia_general_y_especifica():
    texto = ("• EXPERIENCIA LABORAL GENERAL DE TRES (3) AÑOS EN EL SECTOR PÚBLICO Y/O PRIVADO. "
             "• EXPERIENCIA LABORAL ESPECÍFICA DE DOS (2) AÑOS EN LA FUNCIÓN Y/O EN LA MATERIA.")
    assert reglas.experiencia_exigida(texto) == {"general": 3.0, "especifica": 2.0}


def test_experiencia_en_una_sola_frase():
    texto = "02 AÑOS DE EXPERIENCIA GENERAL, 01 AÑO DE EXPERIENCIA ESPECIFICA RELACIONADAS A LAS FUNCIONES"
    assert reglas.experiencia_exigida(texto) == {"general": 2.0, "especifica": 1.0}


def test_experiencia_en_meses():
    assert reglas.experiencia_exigida("SEIS (06) MESES DE EXPERIENCIA LABORAL")["general"] == 0.5


def test_regimen():
    assert reglas.regimen("D.LEG 1057 - DETERMINADO (SUPLENCIA)-08") == "CAS (D. Leg. 1057)"


def test_veredicto_verde_y_rojo():
    oferta = {"formacion": "BACHILLER UNIVERSITARIO EN SOCIOLOGÍA O CIENCIA POLÍTICA",
              "experiencia": "EXPERIENCIA GENERAL DE UN (01) AÑO. EXPERIENCIA ESPECÍFICA DE SEIS (06) MESES EN LA FUNCIÓN.",
              "numero_convocatoria": "D.LEG 1057 - INDETERMINADO-12"}
    perfil = {"carrera": "Ciencia Política", "nivel": TITULO, "colegiado": False,
              "exp_general": 1.5, "exp_especifica": 1.0}
    assert reglas.veredicto(perfil, oferta)["color"] == "verde"
    perfil["exp_general"] = 0.5
    assert reglas.veredicto(perfil, oferta)["color"] == "rojo"
    perfil.update(exp_general=2, carrera="Enfermería")
    assert reglas.veredicto(perfil, oferta)["color"] == "rojo"
