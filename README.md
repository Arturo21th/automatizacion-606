# Automatización del Formato 606

Lee facturas (foto o PDF), extrae los datos con IA, los valida, pide confirmación, y
los guarda en un Excel mensual con el mismo layout que la plantilla oficial de DGII.
Al cierre de mes genera el TXT de envío.

Hay dos formas de usarlo — comparten el mismo motor (`extractor.py`, `validador.py`,
`almacen.py`), solo cambia cómo llega la factura y cómo se confirma:

| | `app.py` (escritorio) | `bot.py` (Telegram) |
|---|---|---|
| Captura | Ella guarda el adjunto de WhatsApp/correo (cae en Descargas); la app lo detecta sola | Ella envía la foto directo al bot desde el celular |
| Confirmación | Ventana en la computadora con los campos editables | Mensaje de chat con botones |
| Corre | Solo cuando ella está en la computadora (no necesita estar 24/7) | Debe quedar corriendo 24/7 en algún lado |

Recomendado para tu caso (ella reenvía las fotos por WhatsApp/correo a sí misma):
**`app.py`**.

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**Solo si vas a usar `app.py`** (la app de escritorio): en Mac con Python de Homebrew,
Tkinter no viene incluido por defecto — instálalo una vez con:

```bash
brew install python-tk@3.14   # ajusta el "3.14" a tu versión de python3 (`python3 --version`)
```

No hace falta recrear el entorno virtual después de instalarlo.

Edita `.env` con:

1. **`ANTHROPIC_API_KEY`**: desde [console.anthropic.com](https://console.anthropic.com) → API Keys.
2. **`EMPRESA_RNC`** / **`EMPRESA_NOMBRE`** (opcional): si los pones, se usan para
   registrar automáticamente tu primera empresa la primera vez que abras la app —
   después, las empresas se administran desde la app misma (ver abajo).
3. **`CARPETA_VIGILADA`** (solo para `app.py`): la carpeta donde caen los adjuntos
   guardados — por defecto `~/Downloads`. Cámbiala si prefieres que use otra.
4. Solo si vas a usar `bot.py`: **`TELEGRAM_BOT_TOKEN`** (habla con
   [@BotFather](https://t.me/BotFather), envía `/newbot`) y opcionalmente
   **`TELEGRAM_CHAT_ID_AUTORIZADO`** para que el bot solo responda a mamá.

## Varias empresas

La app soporta manejar el 606 de **varias empresas distintas** al mismo tiempo —
cada una con su propio Excel por mes, completamente separado. Esto es para el caso
de que la misma persona lleve la contabilidad de más de un negocio (o si en el
futuro más usuarios usan la misma instalación para sus propias empresas).

- Las empresas se administran con el botón **"Administrar empresas"** en la ventana
  principal de `app.py` (o automáticamente al abrir la app por primera vez, si aún
  no hay ninguna registrada). Solo pide RNC + nombre.
- Al revisar una factura, aparece un menú desplegable **"Empresa (quién recibe la
  factura)"**. Si la factura trae impreso el RNC del comprador (algunas facturas de
  Crédito Fiscal lo incluyen), la IA lo detecta y preselecciona la empresa
  automáticamente; si no, o si solo tienes una empresa registrada, queda
  preseleccionada esa. Si es ambigua, hay que elegirla a mano — no se puede
  confirmar una factura sin escoger la empresa.
- Cada empresa guarda sus archivos en su propia carpeta: `datos/{RNC}/606_AAAAMM.xlsx`.
- La revisión de NCF duplicado también es **por empresa** — el mismo NCF puede
  aparecer en dos empresas distintas sin problema (son declaraciones independientes).

## Uso — app de escritorio (`app.py`)

```bash
python app.py
```

Queda una ventanita vigilando la carpeta configurada (por defecto Descargas). Cuando
mamá guarda ahí una foto o PDF de una factura (por ejemplo, al abrir el adjunto de
WhatsApp Web o del correo y darle "Guardar"), la app la detecta sola en unos segundos,
la lee con IA, y abre una ventana de revisión con los campos extraídos — ella puede
corregir cualquier valor antes de confirmar. Botones: **Abrir factura** (para ver la
foto/PDF original), **✅ Confirmar** (guarda en el Excel del mes) o **❌ Descartar**.

> **Nota sobre fotos de iPhone (HEIC):** la API no acepta el formato HEIC que usa el
> iPhone por defecto. Si las fotos llegan como `.heic` y la app no las detecta, activa
> en el iPhone: *Ajustes → Fotos → Transferir a Mac o PC → Automático* (así se
> convierten solas a JPEG al enviarlas/guardarlas), o pídele que las envíe desde la
> app de Cámara/Fotos usando "Compartir → Correo/WhatsApp" (normalmente ya convierte).

## Uso — bot de Telegram (`bot.py`)

Alternativa si prefieres que ella envíe la foto directo desde el celular sin pasar
por la computadora primero. Debe quedar corriendo 24/7 (ver sección de hosting abajo).

```bash
python bot.py
```

Ella envía una foto o PDF de la factura al bot. Si hay una sola empresa registrada
(o la factura trae el RNC del comprador impreso), el bot la detecta sola; si hay
varias y es ambiguo, pregunta por chat "¿para cuál empresa es esta factura?" antes
de mostrar el resumen con los botones ✅ Confirmar / ❌ Descartar. Al confirmar, la
factura se agrega al Excel de esa empresa y mes en `datos/{RNC}/606_AAAAMM.xlsx`.

**Al cierre de mes**, generar el TXT de envío con el botón **"Generar TXT para DGII"**
de la app de escritorio (eliges la empresa y el período). También se puede desde
la terminal (de una empresa específica):

```bash
python generar_txt.py 131667023 202608
```

Esto crea `datos/131667023/DGII_F_606_131667023_202608.TXT` (mismo nombre y layout
que produce la Herramienta Formato 606 oficial de DGII, verificado contra las
macros de su versión 2025). **Antes de subirlo a la Oficina Virtual**, pásalo por
la Herramienta de Prevalidación oficial de DGII para confirmar que no marca errores.

## Estructura

- `config.py` — variables de entorno y catálogos de códigos oficiales de DGII
  (tipo de bienes/servicios, forma de pago, tipo de retención ISR), tomados
  literalmente de la plantilla real `Herramienta Formato 606`.
- `extractor.py` — llama a la API de Claude con la imagen/PDF de la factura y
  devuelve un JSON estricto con los campos del 606.
- `validador.py` — reglas de sanidad (NCF, RNC/Cédula, fechas, ITBIS, duplicados).
- `empresas.py` — registro de empresas (RNC + nombre) gestionable desde la app.
- `almacen.py` — lee/escribe el Excel mensual de cada empresa (24 columnas oficiales).
- `generar_txt.py` — exporta el Excel de una empresa/mes al TXT de envío.
- `app.py` — la app de escritorio que vigila una carpeta y muestra la ventana de revisión.
- `bot.py` — el bot de Telegram, alternativa a `app.py`.

## Dónde correr cada uno

- **`app.py`**: no necesita estar prendido todo el día — mamá lo abre cuando va a
  procesar facturas (por ejemplo, al final del día) y lo cierra cuando termina. Si
  quieres que quede siempre disponible, puedes agregarlo a los "Elementos de inicio
  de sesión" del Mac para que arranque solo al encender la computadora.
- **`bot.py`**: sí necesita estar corriendo 24/7 para que mamá pueda enviar fotos en
  cualquier momento. Opciones: dejarlo corriendo en una computadora que se mantenga
  encendida, o desplegarlo en un VPS barato (~$5/mes) con `systemd` o `pm2` para que
  se reinicie solo si se cae.
