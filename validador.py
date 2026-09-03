"""Validaciones de sanidad para las facturas extraídas antes de guardarlas en el 606."""
from datetime import date

import config


def _digito_verificador_rnc(ocho_digitos: str) -> int:
    """Dígito verificador de un RNC (algoritmo oficial de la Herramienta 606 de DGII):
    suma ponderada con pesos 7,9,8,6,5,4,3,2 módulo 11."""
    pesos = "79865432"
    suma = sum(int(d) * int(p) for d, p in zip(ocho_digitos, pesos))
    resta = suma % 11
    if resta == 0:
        return 2
    if resta == 1:
        return 1
    return 11 - resta


def _digito_verificador_cedula(diez_digitos: str) -> int:
    """Dígito verificador de una cédula dominicana (variante de Luhn con pesos 1,2
    alternados, igual que en la Herramienta 606 de DGII)."""
    suma = 0
    for d, p in zip(diez_digitos, "1212121212"):
        producto = int(d) * int(p)
        suma += producto // 10 + producto % 10
    return (10 - suma % 10) % 10


def validar_rnc_cedula(valor: str, tipo_id: str) -> list[str]:
    errores = []
    limpio = "".join(ch for ch in valor if ch.isdigit())
    if tipo_id == "1":
        if len(limpio) != 9:
            errores.append(f"RNC '{valor}' no tiene 9 dígitos")
        elif _digito_verificador_rnc(limpio[:8]) != int(limpio[8]):
            errores.append(
                f"RNC '{valor}' tiene el dígito verificador incorrecto — "
                "probablemente un número mal leído; compáralo con la factura"
            )
    elif tipo_id == "2":
        if len(limpio) != 11:
            errores.append(f"Cédula '{valor}' no tiene 11 dígitos")
        elif _digito_verificador_cedula(limpio[:10]) != int(limpio[10]):
            errores.append(
                f"Cédula '{valor}' tiene el dígito verificador incorrecto — "
                "probablemente un número mal leído; compárala con la factura"
            )
    return errores


def validar_ncf(ncf: str) -> list[str]:
    if not config.REGEX_NCF.fullmatch(ncf.strip()):
        return [
            f"NCF '{ncf}' no tiene un formato válido (se espera B01-B04/B11-B15/B17 "
            "+ 8 dígitos, o E31-E34/E41-E45/E47 + 10 dígitos)"
        ]
    return []


def validar_ncf_gastos_menores(ncf: str, rnc_proveedor: str, empresa_rnc: str) -> list[str]:
    """Un NCF de gastos menores (B13 físico o E43 electrónico) lo emite la propia
    empresa compradora, así que DGII exige que el RNC informado sea el de la empresa."""
    tipo = ncf.strip().upper()[:3]
    if tipo in ("B13", "E43") and empresa_rnc and rnc_proveedor != empresa_rnc:
        return [
            f"El NCF '{ncf}' es de gastos menores ({tipo}): el RNC debe ser el de tu "
            f"propia empresa ({empresa_rnc}), no el del proveedor"
        ]
    return []


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


def validar_factura(
    datos: dict, facturas_existentes: list[dict], empresa_rnc: str = ""
) -> list[str]:
    """Corre todas las validaciones y devuelve la lista de errores/advertencias encontrados."""
    errores = []
    errores += validar_rnc_cedula(datos["rnc_cedula"], datos["tipo_id"])
    errores += validar_ncf(datos["ncf"])
    errores += validar_ncf_gastos_menores(datos["ncf"], datos["rnc_cedula"], empresa_rnc)
    errores += validar_fecha(datos["fecha_comprobante"], "Fecha de comprobante")
    errores += validar_fecha(datos["fecha_pago"], "Fecha de pago")
    errores += validar_itbis(datos["monto_bienes"], datos["monto_servicios"], datos["itbis_facturado"])
    errores += validar_ncf_duplicado(datos["ncf"], datos["rnc_cedula"], facturas_existentes)
    return errores
