"""Validaciones de sanidad para las facturas extraídas antes de guardarlas en el 606."""
from datetime import date

import config


def validar_rnc_cedula(valor: str, tipo_id: str) -> list[str]:
    errores = []
    limpio = "".join(ch for ch in valor if ch.isdigit())
    if tipo_id == "1" and len(limpio) != 9:
        errores.append(f"RNC '{valor}' no tiene 9 dígitos")
    elif tipo_id == "2" and len(limpio) != 11:
        errores.append(f"Cédula '{valor}' no tiene 11 dígitos")
    return errores


def validar_ncf(ncf: str) -> list[str]:
    errores = []
    if len(ncf) not in (11, 13):
        errores.append(f"NCF '{ncf}' no tiene 11 o 13 caracteres")
    if not any(ncf.upper().startswith(p) for p in config.PREFIJOS_NCF_VALIDOS):
        errores.append(f"Prefijo de NCF '{ncf[:3].upper()}' no reconocido")
    return errores


def validar_fecha(fecha: str, campo: str) -> list[str]:
    errores = []
    if len(fecha) != 8 or not fecha.isdigit():
        errores.append(f"{campo} '{fecha}' no tiene formato AAAAMMDD")
        return errores
    try:
        anio, mes, dia = int(fecha[:4]), int(fecha[4:6]), int(fecha[6:8])
        if date(anio, mes, dia) > date.today():
            errores.append(f"{campo} '{fecha}' está en el futuro")
    except ValueError:
        errores.append(f"{campo} '{fecha}' no es una fecha válida")
    return errores


def validar_itbis(monto_bienes: float, monto_servicios: float, itbis: float, tolerancia: float = 0.05) -> list[str]:
    errores = []
    subtotal = monto_bienes + monto_servicios
    if subtotal > 0 and itbis > 0:
        esperado = subtotal * 0.18
        if abs(itbis - esperado) / esperado > tolerancia:
            errores.append(f"ITBIS {itbis} no cuadra con el 18% de {subtotal} (esperado ~{esperado:.2f})")
    return errores


def validar_ncf_duplicado(ncf: str, rnc_proveedor: str, facturas_existentes: list[dict]) -> list[str]:
    for f in facturas_existentes:
        if f.get("ncf") == ncf and f.get("rnc_cedula") == rnc_proveedor:
            return [f"NCF '{ncf}' del proveedor {rnc_proveedor} ya fue registrado este mes"]
    return []


def validar_factura(datos: dict, facturas_existentes: list[dict]) -> list[str]:
    """Corre todas las validaciones y devuelve la lista de errores/advertencias encontrados."""
    errores = []
    errores += validar_rnc_cedula(datos["rnc_cedula"], datos["tipo_id"])
    errores += validar_ncf(datos["ncf"])
    errores += validar_fecha(datos["fecha_comprobante"], "Fecha de comprobante")
    errores += validar_fecha(datos["fecha_pago"], "Fecha de pago")
    errores += validar_itbis(datos["monto_bienes"], datos["monto_servicios"], datos["itbis_facturado"])
    errores += validar_ncf_duplicado(datos["ncf"], datos["rnc_cedula"], facturas_existentes)
    return errores
