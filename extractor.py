"""Extracción de campos del Formato 606 a partir de una foto o PDF de factura,
usando la API de Claude (visión + salida JSON estricta).
"""
import base64
import json
import mimetypes
from pathlib import Path

import anthropic

import config

_CLIENT = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

_CATALOGO_BIENES = "\n".join(f"{k} - {v}" for k, v in config.TIPO_BIENES_SERVICIOS.items())
_CATALOGO_PAGO = "\n".join(f"{k} - {v}" for k, v in config.FORMA_PAGO.items())

_SCHEMA = {
    "type": "object",
    "properties": {
        "proveedor_nombre": {
            "type": "string",
            "description": "Nombre o razón social del proveedor, tal como aparece en la factura",
        },
        "rnc_cedula": {
            "type": "string",
            "description": "RNC (9 dígitos) o Cédula (11 dígitos) del proveedor, solo números",
        },
        "tipo_id": {
            "type": "string",
            "enum": ["1", "2"],
            "description": "1 si es RNC, 2 si es Cédula",
        },
        "ncf": {
            "type": "string",
            "description": "Número de Comprobante Fiscal completo (NCF o e-NCF), ej: E310000012345 o B0100001234",
        },
        "ncf_modificado": {
            "type": ["string", "null"],
            "description": "NCF que modifica esta nota de crédito/débito, si aplica; null si no aplica",
        },
        "rnc_receptor": {
            "type": ["string", "null"],
            "description": (
                "RNC de la empresa que RECIBE la factura (el comprador/cliente), si aparece "
                "impreso en la factura, ej. en un campo 'Cliente:', 'Señor(es):', 'RNC Cliente:'. "
                "Es DISTINTO del RNC del proveedor. Muchas facturas de consumo no lo incluyen — "
                "en ese caso usa null en vez de adivinar."
            ),
        },
        "fecha_comprobante": {
            "type": "string",
            "description": "Fecha de la factura en formato AAAAMMDD",
        },
        "fecha_pago": {
            "type": "string",
            "description": "Fecha de pago en formato AAAAMMDD; si no se sabe, usar la misma que fecha_comprobante",
        },
        "monto_bienes": {
            "type": "number",
            "description": "Monto facturado en bienes (sin ITBIS); 0 si la factura es solo de servicios",
        },
        "monto_servicios": {
            "type": "number",
            "description": "Monto facturado en servicios (sin ITBIS); 0 si la factura es solo de bienes",
        },
        "itbis_facturado": {
            "type": "number",
            "description": "Monto del ITBIS facturado (usualmente 18% del subtotal); 0 si no aplica",
        },
        "monto_propina_legal": {
            "type": "number",
            "description": "Monto de la propina legal (10%, solo restaurantes/hoteles); 0 si no aplica",
        },
        "tipo_bien_servicio_sugerido": {
            "type": "string",
            "description": (
                "Código de 2 dígitos que mejor clasifica la compra según este catálogo "
                f"oficial de DGII:\n{_CATALOGO_BIENES}"
            ),
        },
        "forma_pago_sugerida": {
            "type": "string",
            "description": f"Código de 2 dígitos de la forma de pago según este catálogo oficial de DGII:\n{_CATALOGO_PAGO}",
        },
        "notas": {
            "type": "string",
            "description": "Dudas, datos ilegibles o ambigüedades que el humano deba revisar antes de confirmar; cadena vacía si no hay dudas",
        },
    },
    "required": [
        "proveedor_nombre",
        "rnc_cedula",
        "tipo_id",
        "ncf",
        "ncf_modificado",
        "rnc_receptor",
        "fecha_comprobante",
        "fecha_pago",
        "monto_bienes",
        "monto_servicios",
        "itbis_facturado",
        "monto_propina_legal",
        "tipo_bien_servicio_sugerido",
        "forma_pago_sugerida",
        "notas",
    ],
    "additionalProperties": False,
}

_PROMPT = (
    "Eres un asistente que extrae datos de facturas dominicanas para el Formato 606 de la DGII. "
    "Analiza la imagen o PDF de la factura adjunta y extrae los campos solicitados con la mayor "
    "precisión posible. Si un dato no aparece o no puedes leerlo con certeza, indícalo en 'notas' "
    "en vez de adivinar. Los montos deben ser números sin símbolo de moneda ni separadores de miles."
)


def _media_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


def extraer_factura(ruta_archivo: str) -> dict:
    """Envía una foto o PDF de factura a Claude y devuelve los campos del 606 en un dict."""
    path = Path(ruta_archivo)
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    media_type = _media_type(path)

    if media_type == "application/pdf":
        content_block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    else:
        content_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        }

    response = _CLIENT.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": [content_block, {"type": "text", "text": _PROMPT}],
            }
        ],
    )

    texto = next(bloque.text for bloque in response.content if bloque.type == "text")
    return json.loads(texto)
