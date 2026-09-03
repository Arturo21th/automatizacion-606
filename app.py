"""App de escritorio: vigila una carpeta (por defecto Descargas) y muestra cada
factura nueva para que la revises y confirmes antes de guardarla en el 606.

Flujo pensado para cuando las fotos llegan por WhatsApp/correo a la misma
computadora: mamá guarda el adjunto (cae normalmente en Descargas) y esta app
lo detecta sola, sin que ella tenga que abrir nada más.
"""
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from dotenv import set_key

import almacen
import config
import empresas
import extractor
import generar_txt
import validador

# HEIC (formato por defecto de fotos de iPhone) no es un tipo de imagen soportado
# por la API de Claude — por eso no se incluye aquí. Ver README para cómo evitarlo.
EXTENSIONES_VALIDAS = {".jpg", ".jpeg", ".png", ".pdf"}

_NUEVA_EMPRESA = "+ Agregar nueva empresa..."

_cola_resultados: "queue.Queue" = queue.Queue()
_vistos: set[str] = set()
_ruta_vistos = config.CARPETA_DATOS / "vistos.json"


def _cargar_vistos() -> None:
    config.CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    if _ruta_vistos.exists():
        _vistos.update(json.loads(_ruta_vistos.read_text()))


def _guardar_vistos() -> None:
    _ruta_vistos.write_text(json.dumps(sorted(_vistos)))


def _abrir_con_visor(ruta: Path) -> None:
    sistema = platform.system()
    if sistema == "Darwin":
        subprocess.run(["open", str(ruta)])
    elif sistema == "Windows":
        os.startfile(str(ruta))  # noqa: solo existe en Windows; ok porque sistema == "Windows"
    else:
        subprocess.run(["xdg-open", str(ruta)])


class DialogoConfiguracionInicial(tk.Toplevel):
    """Primer arranque sin API key configurada: cada instalación/usuario pone la
    suya — así nunca se comparte una key entre distintos usuarios del programa."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Configuración inicial")
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._salir)

        marco = ttk.Frame(self, padding=20)
        marco.pack(fill="both", expand=True)

        ttk.Label(
            marco,
            text="Para leer facturas con IA, esta app necesita tu propia API key de Anthropic.",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))
        ttk.Label(
            marco,
            text="Consíguela gratis en console.anthropic.com → API Keys.",
            foreground="gray",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        ttk.Label(marco, text="API Key de Anthropic:").pack(anchor="w")
        self.var_key = tk.StringVar()
        ttk.Entry(marco, textvariable=self.var_key, width=45, show="•").pack(pady=(2, 12))

        botones = ttk.Frame(marco)
        botones.pack()
        ttk.Button(botones, text="Salir", command=self._salir).pack(side="left", padx=4)
        ttk.Button(botones, text="Guardar y continuar", command=self._guardar).pack(
            side="left", padx=4
        )

    def _salir(self) -> None:
        sys.exit(0)

    def _guardar(self) -> None:
        key = self.var_key.get().strip()
        if not key.startswith("sk-ant-") or len(key) < 20:
            messagebox.showerror(
                "Key inválida", "La API key de Anthropic debe empezar con 'sk-ant-'."
            )
            return

        ruta_env = config.RUTA_ENV_USUARIO
        ruta_env.parent.mkdir(parents=True, exist_ok=True)
        ruta_env.touch(exist_ok=True)
        set_key(str(ruta_env), "ANTHROPIC_API_KEY", key)

        messagebox.showinfo("Listo", "Guardado. La aplicación se va a reiniciar.")
        self.destroy()
        self.master.destroy()
        os.execv(sys.executable, [sys.executable] + sys.argv)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Formato 606 — Revisor de facturas")

        if not config.ANTHROPIC_API_KEY:
            self.withdraw()
            DialogoConfiguracionInicial(self)
            return

        self.geometry("480x150")

        self.carpeta = Path(config.CARPETA_VIGILADA).expanduser()

        marco_superior = ttk.Frame(self)
        marco_superior.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Button(
            marco_superior, text="Administrar empresas", command=self._abrir_gestion_empresas
        ).pack(side="right")
        ttk.Button(
            marco_superior, text="Generar TXT para DGII", command=self._abrir_generar_txt
        ).pack(side="right", padx=(0, 4))

        self.label_estado = ttk.Label(
            self,
            text=f"Vigilando: {self.carpeta}\nEsperando facturas nuevas...",
            padding=20,
            justify="left",
        )
        self.label_estado.pack(fill="both", expand=True)

        self._dialogo_abierto = False
        self._cola_pendientes: list[Path] = []

        if not empresas.listar():
            self.after(300, self._abrir_gestion_empresas)

        self.after(500, self._primer_escaneo)

    def _abrir_gestion_empresas(self) -> None:
        DialogoEmpresas(self)

    def _abrir_generar_txt(self) -> None:
        if not empresas.listar():
            messagebox.showerror(
                "Sin empresas", "Primero registra una empresa en 'Administrar empresas'."
            )
            return
        DialogoGenerarTxt(self)

    def _primer_escaneo(self) -> None:
        # Marca todo lo que ya está en la carpeta como "visto" para no reprocesar
        # archivos viejos que no tienen nada que ver con facturas.
        for archivo in self.carpeta.iterdir():
            if archivo.suffix.lower() in EXTENSIONES_VALIDAS:
                _vistos.add(str(archivo.resolve()))
        _guardar_vistos()
        self.after(3000, self._revisar_carpeta)

    def _revisar_carpeta(self) -> None:
        try:
            for archivo in self.carpeta.iterdir():
                clave = str(archivo.resolve())
                if (
                    archivo.suffix.lower() in EXTENSIONES_VALIDAS
                    and clave not in _vistos
                    and archivo not in self._cola_pendientes
                ):
                    self._cola_pendientes.append(archivo)
        except FileNotFoundError:
            pass

        if self._cola_pendientes and not self._dialogo_abierto:
            self._procesar_siguiente()

        self.after(3000, self._revisar_carpeta)

    def _procesar_siguiente(self) -> None:
        archivo = self._cola_pendientes.pop(0)
        _vistos.add(str(archivo.resolve()))
        _guardar_vistos()
        self._dialogo_abierto = True
        self.label_estado.config(text=f"Vigilando: {self.carpeta}\nLeyendo {archivo.name}...")

        def trabajar():
            try:
                datos = extractor.extraer_factura(str(archivo))
                _cola_resultados.put(("ok", archivo, datos))
            except Exception as exc:
                _cola_resultados.put(("error", archivo, str(exc)))

        threading.Thread(target=trabajar, daemon=True).start()
        self.after(500, self._revisar_resultado)

    def _revisar_resultado(self) -> None:
        try:
            estado, archivo, dato = _cola_resultados.get_nowait()
        except queue.Empty:
            self.after(500, self._revisar_resultado)
            return

        self.label_estado.config(text=f"Vigilando: {self.carpeta}\nEsperando facturas nuevas...")

        if estado == "error":
            messagebox.showerror(
                "Error al leer la factura",
                f"No pude leer {archivo.name}:\n{dato}\n\n"
                "Quedará sin procesar; puedes intentar de nuevo con otra foto.",
            )
            self._dialogo_abierto = False
            return

        DialogoRevision(self, archivo, dato, self._al_cerrar_dialogo)

    def _al_cerrar_dialogo(self) -> None:
        self._dialogo_abierto = False
        if self._cola_pendientes:
            self.after(300, self._procesar_siguiente)


class DialogoEmpresas(tk.Toplevel):
    """Ventana para agregar o eliminar empresas (cada una lleva su propio 606)."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Empresas")
        self.resizable(False, False)
        self.grab_set()

        marco = ttk.Frame(self, padding=16)
        marco.pack(fill="both", expand=True)

        ttk.Label(marco, text="Empresas registradas (cada una tiene su propio 606):").pack(
            anchor="w"
        )
        self.lista = tk.Listbox(marco, width=45, height=6)
        self.lista.pack(pady=(4, 8), fill="both", expand=True)
        self._recargar_lista()

        ttk.Button(marco, text="Eliminar seleccionada", command=self._eliminar).pack(anchor="w")

        ttk.Separator(marco, orient="horizontal").pack(fill="x", pady=10)

        ttk.Label(marco, text="Agregar empresa nueva:").pack(anchor="w")
        marco_form = ttk.Frame(marco)
        marco_form.pack(fill="x", pady=4)
        ttk.Label(marco_form, text="RNC:").grid(row=0, column=0, sticky="w")
        self.var_rnc = tk.StringVar()
        ttk.Entry(marco_form, textvariable=self.var_rnc, width=20).grid(row=0, column=1, padx=4)
        ttk.Label(marco_form, text="Nombre:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.var_nombre = tk.StringVar()
        ttk.Entry(marco_form, textvariable=self.var_nombre, width=30).grid(
            row=1, column=1, padx=4, pady=(4, 0)
        )
        ttk.Button(marco, text="Agregar", command=self._agregar).pack(anchor="e", pady=(8, 0))
        ttk.Button(marco, text="Cerrar", command=self.destroy).pack(anchor="e", pady=(8, 0))

    def _recargar_lista(self) -> None:
        self.lista.delete(0, tk.END)
        for empresa in empresas.listar():
            self.lista.insert(tk.END, f'{empresa["rnc"]} - {empresa["nombre"]}')

    def _agregar(self) -> None:
        try:
            empresas.agregar(self.var_rnc.get(), self.var_nombre.get())
        except ValueError as exc:
            messagebox.showerror("Dato inválido", str(exc))
            return
        self.var_rnc.set("")
        self.var_nombre.set("")
        self._recargar_lista()

    def _eliminar(self) -> None:
        seleccion = self.lista.curselection()
        if not seleccion:
            return
        rnc = self.lista.get(seleccion[0]).split(" - ")[0]
        empresas.eliminar(rnc)
        self._recargar_lista()


class DialogoGenerarTxt(tk.Toplevel):
    """Elige empresa y período, y genera el archivo .txt de envío a DGII."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Generar TXT para DGII")
        self.resizable(False, False)
        self.grab_set()

        marco = ttk.Frame(self, padding=16)
        marco.pack(fill="both", expand=True)

        ttk.Label(marco, text="Empresa:").grid(row=0, column=0, sticky="w", pady=2)
        opciones = [f'{e["rnc"]} - {e["nombre"]}' for e in empresas.listar()]
        self.var_empresa = tk.StringVar(value=opciones[0] if len(opciones) == 1 else "")
        ttk.Combobox(
            marco, textvariable=self.var_empresa, values=opciones, width=40, state="readonly"
        ).grid(row=0, column=1, pady=2)

        ttk.Label(marco, text="Período (AAAAMM):").grid(row=1, column=0, sticky="w", pady=2)
        self.var_periodo = tk.StringVar(value=date.today().strftime("%Y%m"))
        ttk.Entry(marco, textvariable=self.var_periodo, width=10).grid(
            row=1, column=1, sticky="w", pady=2
        )

        ttk.Label(
            marco,
            text="Antes de enviarlo a DGII, valida el archivo con la\n"
            "Herramienta de Prevalidación oficial de la Oficina Virtual.",
            foreground="gray",
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        botones = ttk.Frame(marco)
        botones.grid(row=3, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(botones, text="Generar", command=self._generar).pack(side="left", padx=4)
        ttk.Button(botones, text="Cerrar", command=self.destroy).pack(side="left", padx=4)

    def _generar(self) -> None:
        empresa_valor = self.var_empresa.get()
        if not empresa_valor:
            messagebox.showerror("Falta la empresa", "Selecciona una empresa.", parent=self)
            return
        rnc = empresa_valor.split(" - ")[0]

        periodo = self.var_periodo.get().strip()
        if len(periodo) != 6 or not periodo.isdigit():
            messagebox.showerror(
                "Período inválido", "El período debe ser AAAAMM, ej. 202609.", parent=self
            )
            return

        try:
            ruta = generar_txt.generar_txt(rnc, periodo)
        except FileNotFoundError:
            messagebox.showerror(
                "Sin datos",
                f"No hay facturas guardadas para esa empresa en el período {periodo}.",
                parent=self,
            )
            return

        if messagebox.askyesno(
            "TXT generado",
            f"Archivo generado:\n{ruta}\n\n¿Abrir la carpeta donde quedó guardado?",
            parent=self,
        ):
            _abrir_con_visor(ruta.parent)
        self.destroy()


class DialogoRevision(tk.Toplevel):
    def __init__(self, master, archivo: Path, datos: dict, al_cerrar):
        super().__init__(master)
        self.title(f"Revisar: {archivo.name}")
        self.archivo = archivo
        self.datos = datos
        self.al_cerrar = al_cerrar
        self.resizable(False, False)
        self.grab_set()

        marco = ttk.Frame(self, padding=16)
        marco.pack(fill="both", expand=True)

        self.vars = {}
        campos = [
            ("proveedor_nombre", "Proveedor"),
            ("rnc_cedula", "RNC/Cédula"),
            ("ncf", "NCF"),
            ("fecha_comprobante", "Fecha (AAAAMMDD)"),
            ("monto_bienes", "Monto en Bienes"),
            ("monto_servicios", "Monto en Servicios"),
            ("itbis_facturado", "ITBIS Facturado"),
        ]
        fila = 0
        for clave, etiqueta in campos:
            ttk.Label(marco, text=etiqueta + ":").grid(row=fila, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=str(datos.get(clave, "")))
            ttk.Entry(marco, textvariable=var, width=30).grid(row=fila, column=1, pady=2)
            self.vars[clave] = var
            fila += 1

        ttk.Label(marco, text="Empresa (quién recibe la factura):").grid(
            row=fila, column=0, sticky="w", pady=2
        )
        opciones_empresas = [f'{e["rnc"]} - {e["nombre"]}' for e in empresas.listar()]
        valor_inicial = ""
        if datos.get("rnc_receptor"):
            valor_inicial = next(
                (o for o in opciones_empresas if o.startswith(datos["rnc_receptor"])), ""
            )
        if not valor_inicial and len(opciones_empresas) == 1:
            valor_inicial = opciones_empresas[0]
        self.var_empresa = tk.StringVar(value=valor_inicial)
        self.combo_empresa = ttk.Combobox(
            marco,
            textvariable=self.var_empresa,
            values=opciones_empresas + [_NUEVA_EMPRESA],
            width=40,
            state="readonly",
        )
        self.combo_empresa.grid(row=fila, column=1, pady=2)
        self.combo_empresa.bind("<<ComboboxSelected>>", self._al_cambiar_empresa)
        fila += 1

        ttk.Label(marco, text="Tipo de Bien/Servicio:").grid(row=fila, column=0, sticky="w", pady=2)
        opciones_bienes = [f"{k} - {v}" for k, v in config.TIPO_BIENES_SERVICIOS.items()]
        self.var_tipo_bien = tk.StringVar(
            value=next(
                (o for o in opciones_bienes if o.startswith(datos["tipo_bien_servicio_sugerido"])),
                opciones_bienes[0],
            )
        )
        ttk.Combobox(
            marco, textvariable=self.var_tipo_bien, values=opciones_bienes, width=40, state="readonly"
        ).grid(row=fila, column=1, pady=2)
        fila += 1

        ttk.Label(marco, text="Forma de Pago:").grid(row=fila, column=0, sticky="w", pady=2)
        opciones_pago = [f"{k} - {v}" for k, v in config.FORMA_PAGO.items()]
        self.var_forma_pago = tk.StringVar(
            value=next(
                (o for o in opciones_pago if o.startswith(datos["forma_pago_sugerida"])),
                opciones_pago[0],
            )
        )
        ttk.Combobox(
            marco, textvariable=self.var_forma_pago, values=opciones_pago, width=40, state="readonly"
        ).grid(row=fila, column=1, pady=2)
        fila += 1

        if datos.get("notas"):
            ttk.Label(
                marco, text=f"⚠️ Nota de la IA: {datos['notas']}", foreground="darkorange", wraplength=380
            ).grid(row=fila, column=0, columnspan=2, sticky="w", pady=(8, 0))
            fila += 1

        self.label_errores = ttk.Label(marco, text="", foreground="red", wraplength=380, justify="left")
        self.label_errores.grid(row=fila, column=0, columnspan=2, sticky="w", pady=(8, 0))
        fila += 1

        botones = ttk.Frame(marco)
        botones.grid(row=fila, column=0, columnspan=2, pady=(16, 0))
        ttk.Button(botones, text="Abrir factura", command=self._abrir).pack(side="left", padx=4)
        ttk.Button(botones, text="✅ Confirmar", command=self._confirmar).pack(side="left", padx=4)
        ttk.Button(botones, text="❌ Descartar", command=self._descartar).pack(side="left", padx=4)

        self.protocol("WM_DELETE_WINDOW", self._descartar)

        # Revalida mientras se editan los campos, con una pequeña espera para no
        # releer el Excel en cada tecla.
        self._revalidacion_programada = None
        for var in list(self.vars.values()) + [self.var_tipo_bien, self.var_forma_pago]:
            var.trace_add("write", self._programar_revalidacion)

        self._revalidar()

    def _programar_revalidacion(self, *_args) -> None:
        if self._revalidacion_programada:
            self.after_cancel(self._revalidacion_programada)
        self._revalidacion_programada = self.after(400, self._revalidar)

    def _abrir(self) -> None:
        _abrir_con_visor(self.archivo)

    def _al_cambiar_empresa(self, event=None) -> None:
        if self.var_empresa.get() == _NUEVA_EMPRESA:
            self._agregar_empresa_rapido()
        self._revalidar()

    def _agregar_empresa_rapido(self) -> None:
        rnc = simpledialog.askstring("Nueva empresa", "RNC de la empresa:", parent=self)
        if not rnc:
            self.var_empresa.set("")
            return
        nombre = simpledialog.askstring("Nueva empresa", "Nombre de la empresa:", parent=self)
        if not nombre:
            self.var_empresa.set("")
            return
        try:
            empresas.agregar(rnc, nombre)
        except ValueError as exc:
            messagebox.showerror("Dato inválido", str(exc))
            self.var_empresa.set("")
            return

        nueva_opcion = f'{"".join(ch for ch in rnc if ch.isdigit())} - {nombre.strip()}'
        opciones = [o for o in self.combo_empresa["values"] if o != _NUEVA_EMPRESA]
        if nueva_opcion not in opciones:
            opciones.append(nueva_opcion)
        opciones.append(_NUEVA_EMPRESA)
        self.combo_empresa["values"] = opciones
        self.var_empresa.set(nueva_opcion)

    def _revalidar(self) -> None:
        self._revalidacion_programada = None
        try:
            datos_actuales = self._valores_finales()
        except ValueError:
            self.label_errores.config(
                text="🚫 Revisar:\n- Hay montos que no son números válidos"
            )
            return

        empresa_valor = self.var_empresa.get()
        empresa_rnc = ""
        facturas_existentes = []
        if empresa_valor and empresa_valor != _NUEVA_EMPRESA:
            empresa_rnc = empresa_valor.split(" - ")[0]
            periodo = datos_actuales["fecha_comprobante"][:6]
            facturas_existentes = almacen.cargar_facturas(empresa_rnc, periodo)

        errores = validador.validar_factura(datos_actuales, facturas_existentes, empresa_rnc)
        if errores:
            self.label_errores.config(text="🚫 Revisar:\n" + "\n".join(f"- {e}" for e in errores))
        else:
            self.label_errores.config(text="")

    def _valores_finales(self) -> dict:
        datos = dict(self.datos)
        datos["proveedor_nombre"] = self.vars["proveedor_nombre"].get()
        datos["rnc_cedula"] = self.vars["rnc_cedula"].get()
        datos["ncf"] = self.vars["ncf"].get()
        datos["fecha_comprobante"] = self.vars["fecha_comprobante"].get()
        datos["fecha_pago"] = datos.get("fecha_pago") or datos["fecha_comprobante"]
        datos["monto_bienes"] = float(self.vars["monto_bienes"].get() or 0)
        datos["monto_servicios"] = float(self.vars["monto_servicios"].get() or 0)
        datos["itbis_facturado"] = float(self.vars["itbis_facturado"].get() or 0)
        datos["tipo_bien_servicio_sugerido"] = self.var_tipo_bien.get().split(" - ")[0]
        datos["forma_pago_sugerida"] = self.var_forma_pago.get().split(" - ")[0]
        return datos

    def _confirmar(self) -> None:
        empresa_valor = self.var_empresa.get()
        if not empresa_valor or empresa_valor == _NUEVA_EMPRESA:
            messagebox.showerror(
                "Falta la empresa",
                "Selecciona a qué empresa pertenece esta factura antes de confirmar.",
            )
            return
        empresa_rnc = empresa_valor.split(" - ")[0]

        try:
            datos = self._valores_finales()
        except ValueError as exc:
            messagebox.showerror("Dato inválido", f"Revisa los campos: {exc}")
            return

        periodo = datos["fecha_comprobante"][:6]
        errores = validador.validar_factura(
            datos, almacen.cargar_facturas(empresa_rnc, periodo), empresa_rnc
        )
        if errores and not messagebox.askyesno(
            "Advertencias encontradas",
            "Antes de guardar, revisa esto:\n"
            + "\n".join(f"- {e}" for e in errores)
            + "\n\n¿Guardar de todas formas?",
            parent=self,
        ):
            return

        try:
            linea = almacen.agregar_factura(empresa_rnc, periodo, datos)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Dato inválido", f"Revisa los campos: {exc}")
            return

        carpeta_ok = config.CARPETA_DATOS / "procesadas"
        carpeta_ok.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.archivo), carpeta_ok / self.archivo.name)
        messagebox.showinfo("Guardado", f"Guardada como línea {linea} del período {periodo}.")
        self.destroy()
        self.al_cerrar()

    def _descartar(self) -> None:
        carpeta_desc = config.CARPETA_DATOS / "descartadas"
        carpeta_desc.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.archivo), carpeta_desc / self.archivo.name)
        self.destroy()
        self.al_cerrar()


if __name__ == "__main__":
    _cargar_vistos()
    app = App()
    app.mainloop()
