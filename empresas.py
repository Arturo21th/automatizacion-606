"""Registro de empresas (RNC + nombre) que este usuario administra en el 606.

Cada empresa tiene su propio Excel/606 por mes (ver almacen.py). La lista se
persiste en datos/empresas.json y se administra desde la app, no editando código
— así cualquier usuario de la app puede agregar sus propias empresas.
"""
import json
from pathlib import Path

import config

_RUTA = config.CARPETA_DATOS / "empresas.json"


def listar() -> list[dict]:
    """Devuelve la lista de empresas registradas: [{'rnc': ..., 'nombre': ...}, ...]."""
    _sembrar_desde_env_si_esta_vacio()
    if not _RUTA.exists():
        return []
    return json.loads(_RUTA.read_text())


def agregar(rnc: str, nombre: str) -> None:
    rnc = "".join(ch for ch in rnc if ch.isdigit())
    nombre = nombre.strip()
    if not rnc or not nombre:
        raise ValueError("El RNC y el nombre de la empresa no pueden estar vacíos")

    empresas = listar()
    if any(e["rnc"] == rnc for e in empresas):
        return  # ya existe, no duplicar
    empresas.append({"rnc": rnc, "nombre": nombre})
    _guardar(empresas)


def eliminar(rnc: str) -> None:
    empresas = [e for e in listar() if e["rnc"] != rnc]
    _guardar(empresas)


def buscar_por_rnc(rnc: str) -> dict | None:
    for empresa in listar():
        if empresa["rnc"] == rnc:
            return empresa
    return None


def _guardar(empresas: list[dict]) -> None:
    config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    _RUTA.write_text(json.dumps(empresas, ensure_ascii=False, indent=2))


def _sembrar_desde_env_si_esta_vacio() -> None:
    """Si nunca se ha registrado ninguna empresa pero .env tiene EMPRESA_RNC/NOMBRE
    (configuración de instalaciones previas a este registro), la usa como semilla."""
    if _RUTA.exists():
        return
    if config.EMPRESA_RNC and config.EMPRESA_NOMBRE:
        _guardar([{"rnc": config.EMPRESA_RNC, "nombre": config.EMPRESA_NOMBRE}])
