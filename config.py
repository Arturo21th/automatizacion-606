"""Configuración y catálogos oficiales del Formato 606 de la DGII.

Los catálogos de códigos (TIPO_BIENES_SERVICIOS, FORMA_PAGO, TIPO_RETENCION_ISR)
fueron extraídos literalmente de la plantilla oficial de DGII
"Herramienta Formato 606" (columnas de listas desplegables), para que la
clasificación que hace la IA use exactamente las mismas opciones que espera DGII.
"""
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Cuando corre como .exe empaquetado (PyInstaller), sys.executable apunta al propio
# ejecutable — ahí es donde el instalador deja el .env con la API key.
if getattr(sys, "frozen", False):
    CARPETA_BASE = Path(sys.executable).resolve().parent
else:
    CARPETA_BASE = Path(__file__).resolve().parent

# Carpeta donde la app puede ESCRIBIR (datos, vistos.json, .env del usuario).
# Instalada en Windows, el .exe vive en C:\Program Files, que es de solo lectura
# para usuarios normales — escribir ahí da "Acceso denegado" (WinError 5). Por eso
# los datos van a %LOCALAPPDATA%\Formato606. Corriendo desde el código fuente,
# todo queda junto al proyecto, como siempre.
if getattr(sys, "frozen", False):
    if os.name == "nt":
        CARPETA_ESCRITURA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Formato606"
    else:
        CARPETA_ESCRITURA = Path.home() / "Formato606"
else:
    CARPETA_ESCRITURA = CARPETA_BASE

# El .env del usuario (si alguna vez configuró su propia key) tiene prioridad
# sobre el .env que viene con el instalador; load_dotenv no pisa valores ya cargados.
RUTA_ENV_USUARIO = CARPETA_ESCRITURA / ".env"
load_dotenv(RUTA_ENV_USUARIO)
load_dotenv(CARPETA_BASE / ".env")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
EMPRESA_RNC = os.environ.get("EMPRESA_RNC", "")
EMPRESA_NOMBRE = os.environ.get("EMPRESA_NOMBRE", "")
TELEGRAM_CHAT_ID_AUTORIZADO = os.environ.get("TELEGRAM_CHAT_ID_AUTORIZADO", "")
CARPETA_DATOS = Path(os.environ.get("CARPETA_DATOS", str(CARPETA_ESCRITURA / "datos")))

# Carpeta que la app de escritorio vigila en busca de facturas nuevas (fotos/PDF).
CARPETA_VIGILADA = os.environ.get("CARPETA_VIGILADA", str(Path.home() / "Downloads"))

# --- Catálogo: Tipo de Bienes y Servicios Comprados ---
TIPO_BIENES_SERVICIOS = {
    "01": "GASTOS DE PERSONAL",
    "02": "GASTOS POR TRABAJOS, SUMINISTROS Y SERVICIOS",
    "03": "ARRENDAMIENTOS",
    "04": "GASTOS DE ACTIVOS FIJO",
    "05": "GASTOS DE REPRESENTACIÓN",
    "06": "OTRAS DEDUCCIONES ADMITIDAS",
    "07": "GASTOS FINANCIEROS",
    "08": "GASTOS EXTRAORDINARIOS",
    "09": "COMPRAS Y GASTOS QUE FORMARAN PARTE DEL COSTO DE VENTA",
    "10": "ADQUISICIONES DE ACTIVOS",
    "11": "GASTOS DE SEGUROS",
}

# --- Catálogo: Forma de Pago ---
FORMA_PAGO = {
    "01": "EFECTIVO",
    "02": "CHEQUES/TRANSFERENCIAS/DEPÓSITO",
    "03": "TARJETA CRÉDITO/DÉBITO",
    "04": "COMPRA A CREDITO",
    "05": "PERMUTA",
    "06": "NOTA DE CREDITO",
    "07": "MIXTO",
}

# --- Catálogo: Tipo de Retención en ISR ---
TIPO_RETENCION_ISR = {
    "00": "",
    "01": "ALQUILERES",
    "02": "HONORARIOS POR SERVICIOS",
    "03": "OTRAS RENTAS",
    "04": "OTRAS RENTAS (Rentas Presuntas)",
    "05": "INTERESES PAGADOS A PERSONAS JURIDICAS RESIDENTES",
    "06": "INTERESES PAGADOS A PERSONAS FISICAS RESIDENTES",
    "07": "RETENCION POR PROVEEDORES DEL ESTADO",
    "08": "JUEGOS TELEFONICOS",
    "09": "RETENCIONES SUBSECTOR DE GANADERÍA DE CARNE BOVINA",
}

# --- Formato válido de NCF / e-NCF ---
# Expresión regular tomada literalmente de las macros de la "Herramienta
# Formato 606" oficial de DGII (versión 2025, constante strRegexNcf):
# series antiguas de 19 caracteres (A/P/Q), NCF físicos de 11 (B01-B04,
# B11-B15, B17) y e-CF de 13 (E31-E34, E41-E45, E47).
REGEX_NCF = re.compile(
    r"(?:[AQPaqp][0-9]{8}(?:0[1-4]|1[1-5])[0-9]{8})"
    r"|(?:[Bb](?:0[1-4]|1[1-5]|17)[0-9]{8})"
    r"|(?:[Ee](?:3[1-4]|4[1-5]|47)[0-9]{10})"
)

# Las 24 columnas del Formato 606 en el orden exacto de la plantilla oficial de DGII.
COLUMNAS_606 = [
    "Linea",
    "RNC o Cedula",
    "Tipo Id",
    "Tipo Bienes y Servicios Comprados",
    "NCF",
    "NCF o Documento Modificado",
    "Fecha Comprobante",
    "Fecha Pago",
    "Monto Facturado en Servicios",
    "Monto Facturado en Bienes",
    "Total Monto Facturado",
    "ITBIS Facturado",
    "ITBIS Retenido",
    "ITBIS sujeto a Proporcionalidad",
    "ITBIS llevado al Costo",
    "ITBIS por Adelantar",
    "ITBIS percibido en compras",
    "Tipo de Retencion en ISR",
    "Monto Retencion Renta",
    "ISR Percibido en compras",
    "Impuesto Selectivo al Consumo",
    "Otros Impuesto/Tasas",
    "Monto Propina Legal",
    "Forma de Pago",
]
