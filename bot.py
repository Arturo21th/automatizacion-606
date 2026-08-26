"""Bot de Telegram: mamá envía una foto o PDF de factura y el bot la procesa para el 606."""
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import almacen
import config
import empresas
import extractor
import validador

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Facturas leídas pero aún no confirmadas, por chat_id (una a la vez).
_pendientes: dict[int, dict] = {}


def _autorizado(update: Update) -> bool:
    if not config.TELEGRAM_CHAT_ID_AUTORIZADO:
        return True
    return str(update.effective_chat.id) == str(config.TELEGRAM_CHAT_ID_AUTORIZADO)


def _resumen(datos: dict, empresa_nombre: str, errores: list[str]) -> str:
    total = datos["monto_bienes"] + datos["monto_servicios"]
    texto = (
        f"🏢 *Empresa:* {empresa_nombre}\n"
        f"📄 *Proveedor:* {datos['proveedor_nombre']}\n"
        f"*RNC/Cédula:* {datos['rnc_cedula']}\n"
        f"*NCF:* {datos['ncf']}\n"
        f"*Fecha:* {datos['fecha_comprobante']}\n"
        f"*Monto:* RD${total:,.2f}\n"
        f"*ITBIS:* RD${datos['itbis_facturado']:,.2f}\n"
        f"*Tipo:* {config.TIPO_BIENES_SERVICIOS.get(datos['tipo_bien_servicio_sugerido'], '?')}\n"
        f"*Forma de pago:* {config.FORMA_PAGO.get(datos['forma_pago_sugerida'], '?')}\n"
    )
    if datos.get("notas"):
        texto += f"\n⚠️ *Nota de la IA:* {datos['notas']}\n"
    if errores:
        texto += "\n🚫 *Posibles problemas:*\n" + "\n".join(f"- {e}" for e in errores)
    texto += "\n\n¿Es correcto?"
    return texto


def _texto_lista_empresas() -> str:
    return "\n".join(f'- {e["rnc"]} ({e["nombre"]})' for e in empresas.listar())


async def _mostrar_confirmacion(mensaje, chat_id: int, datos: dict, empresa: dict) -> None:
    periodo = datos["fecha_comprobante"][:6]
    facturas_existentes = almacen.cargar_facturas(empresa["rnc"], periodo)
    errores = validador.validar_factura(datos, facturas_existentes)

    _pendientes[chat_id] = {"datos": datos, "periodo": periodo, "empresa_rnc": empresa["rnc"]}

    botones = [
        [
            InlineKeyboardButton("✅ Confirmar", callback_data="confirmar"),
            InlineKeyboardButton("❌ Descartar", callback_data="descartar"),
        ]
    ]
    await mensaje.reply_text(
        _resumen(datos, empresa["nombre"], errores),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botones),
    )


async def recibir_factura(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        return

    mensaje = update.effective_message
    archivo = None
    nombre = "factura"
    if mensaje.photo:
        archivo = await mensaje.photo[-1].get_file()
        nombre += ".jpg"
    elif mensaje.document:
        archivo = await mensaje.document.get_file()
        nombre = mensaje.document.file_name or (nombre + ".pdf")

    if archivo is None:
        return

    lista_empresas = empresas.listar()
    if not lista_empresas:
        await mensaje.reply_text(
            "Todavía no hay ninguna empresa configurada. Abre la app de escritorio "
            "(app.py) y agrega al menos una empresa antes de enviar facturas por aquí."
        )
        return

    await mensaje.reply_text("Leyendo la factura... 🔍")

    with NamedTemporaryFile(suffix=Path(nombre).suffix or ".jpg", delete=False) as tmp:
        await archivo.download_to_drive(tmp.name)
        ruta_tmp = tmp.name

    try:
        datos = extractor.extraer_factura(ruta_tmp)
    except Exception:
        logger.exception("Error extrayendo datos de la factura")
        await mensaje.reply_text("No pude leer esta factura. ¿Puedes enviar una foto más clara?")
        return
    finally:
        Path(ruta_tmp).unlink(missing_ok=True)

    chat_id = update.effective_chat.id

    empresa = None
    if datos.get("rnc_receptor"):
        empresa = empresas.buscar_por_rnc(datos["rnc_receptor"])
    if empresa is None and len(lista_empresas) == 1:
        empresa = lista_empresas[0]

    if empresa is not None:
        await _mostrar_confirmacion(mensaje, chat_id, datos, empresa)
        return

    # Varias empresas configuradas y no se pudo detectar cuál — se pregunta por texto.
    _pendientes[chat_id] = {"datos": datos, "esperando_empresa": True}
    await mensaje.reply_text(
        "¿Para cuál empresa es esta factura? Responde con el RNC:\n" + _texto_lista_empresas()
    )


async def recibir_respuesta_empresa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        return

    chat_id = update.effective_chat.id
    pendiente = _pendientes.get(chat_id)
    if pendiente is None or not pendiente.get("esperando_empresa"):
        return

    mensaje = update.effective_message
    empresa = empresas.buscar_por_rnc(mensaje.text.strip())
    if empresa is None:
        await mensaje.reply_text(
            "No reconozco ese RNC. Intenta de nuevo con uno de estos:\n" + _texto_lista_empresas()
        )
        return

    await _mostrar_confirmacion(mensaje, chat_id, pendiente["datos"], empresa)


async def manejar_boton(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    pendiente = _pendientes.pop(chat_id, None)

    if pendiente is None or "empresa_rnc" not in pendiente:
        await query.edit_message_text("Ya no hay ninguna factura pendiente.")
        return

    if query.data == "descartar":
        await query.edit_message_text("Factura descartada. Envía otra cuando quieras.")
        return

    linea = almacen.agregar_factura(pendiente["empresa_rnc"], pendiente["periodo"], pendiente["datos"])
    await query.edit_message_text(f"Guardada como línea {linea} del período {pendiente['periodo']}. ✅")


def main() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el .env")

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, recibir_factura))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_respuesta_empresa))
    app.add_handler(CallbackQueryHandler(manejar_boton))
    logger.info("Bot corriendo...")
    app.run_polling()


if __name__ == "__main__":
    main()
