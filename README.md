# ICPPLUS Monitor

Monitor de citas de extranjería con Selenium, avisos por Telegram y panel en
GitHub Pages. Configurado para Madrid, toma de huellas (inicial, renovación,
duplicado y Ley 14/2013), con alias neutro.

## GitHub Actions y Pages

1. Sube el proyecto a tu repositorio con rama `main`.
2. En **Settings → Secrets and variables → Actions**, crea los secretos
   `TELEGRAM_BOT_TOKEN` (BotFather) y `TELEGRAM_CHAT_ID` (chat destinatario).
   Envía `/start` a tu bot. Nunca guardes el token en Git.
   La identificación del solicitante usa otros tres secretos: `ICP_NIE`,
   `ICP_FULL_NAME` y `ICP_NATIONALITY` (texto exacto del país, por ejemplo CHINA).
   Solo se envían al portal oficial para consultar disponibilidad. Con datos
   de identidad configurados se desactivan capturas y volcados HTML.
3. En **Settings → Pages → Source**, elige **GitHub Actions**.
4. En **Actions → ICPPLUS Monitor → Run workflow**, inicia una comprobación.
5. En **Actions → Publish dashboard**, consulta la URL del despliegue.

Comprobación programada **cada 5 minutos, las 24 horas, todos los días**
(`*/5 * * * *`). Está en `.github/workflows/monitor.yml`.
GitHub puede retrasar ejecuciones: el intervalo no está garantizado.
El panel recarga resultados cada minuto;
esto no inicia otra comprobación.

El [diagnóstico de conexión](docs/connection-diagnosis.md) documenta un
timeout al establecer TCP desde Azure al puerto 443 del portal. La consulta
de disponibilidad sigue pendiente mientras no haya conectividad desde el runner.

El panel público incluye `Perfil 1`, provincia, trámite, estado y hora.
Excluye identidad, registros y enlaces de sesión. Los archivos e historial
de un repositorio público también son públicos: usa siempre alias neutros.

## Ejecución local (PowerShell)

Requiere Python 3.11 o superior y Google Chrome:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edita .env con el token y chat ID.
.\.venv\Scripts\python.exe monitor.py --test-telegram
.\.venv\Scripts\python.exe monitor.py
.\.venv\Scripts\python.exe publish_dashboard.py
.\.venv\Scripts\python.exe -m http.server 8000 --bind 127.0.0.1 --directory _site
```

Abre http://127.0.0.1:8000. El monitor comprueba una vez; GitHub Actions lo
repite en la nube. `.env`, el entorno virtual y los diagnósticos se excluyen
de Git. Selenium obtiene el controlador compatible con Chrome.
En entornos restringidos configura `SE_CACHE_PATH`, `TEMP` y `TMP` hacia
carpetas locales con permiso de escritura.

## Perfiles y estados

Edita `data/profiles.json`: `id` único, `name` (alias), `province` y
`procedure_name` con el texto exacto del desplegable. `enabled: false` pausa
un perfil; `selectors` permite ajustar selectores. El texto del trámite de
Madrid se contrastó con el desplegable oficial; la consulta completa aún no
se ha podido validar desde GitHub por el fallo de conexión.

- `available`: se encontró el calendario; se avisa de posible disponibilidad.
- `unavailable`: hay un mensaje explícito de que no hay citas.
- `blocked`: el portal rechaza el acceso o exige CAPTCHA; disponibilidad desconocida.
- `requires_input`: faltan secretos de identificación del solicitante.
- `error`: fallo del navegador, selector o flujo; disponibilidad desconocida.

El flujo usa la entrada vigente `/icpplustiem/index.html`: provincia, trámite,
presentación sin Cl@ve e identificación mediante secretos. Solo pulsa
«Solicitar Cita» para consultar la disponibilidad, sin elegir fecha ni reservar.
Si exige CAPTCHA o SMS, requiere intervención manual.
Un bloqueo o una pantalla desconocida no se interpretan como «sin citas».
La reserva se completa manualmente.

`autofill_userscript.js` es un helper opcional para Tampermonkey con datos
ficticios. No publiques datos reales en él. `GMAIL_EMAIL`, `GMAIL_APP_PASSWORD`
y `ALERT_EMAIL_TO` activan también el correo; no hacen falta para Telegram.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
