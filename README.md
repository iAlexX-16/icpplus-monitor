# ICPPLUS Monitor

Monitor de citas de extranjería con Chrome, avisos por Telegram y panel en
GitHub Pages. Configurado para Madrid, toma de huellas (inicial, renovación,
duplicado y Ley 14/2013), con alias neutro. Las comprobaciones automáticas se
ejecutan en Windows cada quince minutos, usando un perfil propio de Chrome.

## Ejecución automática en Windows

La tarea **ICPPLUS Monitor (local)** ejecuta `local_runner.ps1 -QuarterHour`
a los minutos **:14, :29, :44 y :59**. Prepara la sesión y el formulario,
y retiene el envío hasta **:00, :15, :30 o :45**. El usuario debe mantener la sesión de Windows iniciada y el equipo
encendido, despierto y conectado a Internet. Chrome se muestra durante cada
comprobación y se cierra al terminar. No se necesita una ventana de terminal.

El objetivo controla la hora de envío desde el ordenador; la respuesta y
los pasos adicionales del servidor pueden llegar después. El resultado
incluye la hora prevista, la preparación, el inicio de consulta y, si hace
falta una segunda petición, la hora de esa petición de disponibilidad.
Una preparación retrasada más de un segundo no envía una consulta tardía:
queda como `missed`. Una ejecución iniciada fuera del minuto de preparación
se omite. La sincronización horaria admite un único perfil activo.

Los secretos locales se guardan cifrados con DPAPI para el usuario de Windows
actual en `.local/secrets.json`. El perfil `.local/chrome-profile` es exclusivo
del monitor; no copia cookies del perfil personal. `.local/` está excluido de Git.

Para preparar otra instalación, crea el entorno virtual e instala
`requirements.txt`, luego pasa un JSON por la entrada estándar a
`configure_local_secrets.ps1` con las claves `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, `ICP_NIE`, `ICP_FULL_NAME` e `ICP_NATIONALITY`.
Los valores no deben guardarse en un archivo de código ni en el repositorio.

```powershell
# Inicio de sesión para publicar el panel; se guarda en el Administrador de credenciales.
git credential-manager github login --username iAlexX-16 --device
# Primera comprobación y registro de la tarea.
.\local_runner.ps1
.\install_local_task.ps1
Get-ScheduledTaskInfo -TaskName 'ICPPLUS Monitor (local)'
```

El log local está en `.local/monitor.log`; el resultado, en `data/status.json`.
`publish_local_status.py` publica únicamente estado, hora y un enlace público,
sin datos de identidad, registros ni enlaces de sesión. GitHub Pages se
actualiza al recibir esos resultados. Las ejecuciones locales no se solapan.

Un rechazo del portal durante la preparación admite un único reinicio de
sesión, solo si quedan al menos 35 segundos antes del objetivo. CAPTCHA,
403 y fallos posteriores al envío de identidad no se reintentan. Las
consultas fallidas se publican con su estado real y terminan con error,
en lugar de devolver código 0. Los resultados antiguos no se republican
cuando una ejecución no genera un nuevo estado.

Para pausar o reactivar la tarea:

```powershell
Disable-ScheduledTask -TaskName 'ICPPLUS Monitor (local)'
Enable-ScheduledTask -TaskName 'ICPPLUS Monitor (local)'
```

## Panel en GitHub Pages y comprobación manual en Actions

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

La comprobación automática se ha trasladado a Windows. El workflow
`.github/workflows/monitor.yml` queda disponible solo para ejecución manual,
sin un segundo monitor automático en Azure. El panel recarga resultados
cada minuto; esto no inicia otra comprobación del portal.

El [diagnóstico de conexión](docs/connection-diagnosis.md) documenta el
timeout TCP desde Azure y la prueba local que consiguió consultar la
disponibilidad. El portal puede rechazar sesiones: estos casos se muestran
como `blocked` y no como ausencia de citas.

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

Abre http://127.0.0.1:8000. El monitor comprueba una vez; la tarea de Windows
lo repite en la instalación local. `.env`, el entorno virtual y los diagnósticos se excluyen
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
- `missed`: no se completó la preparación antes del objetivo y no se envió una consulta fuera de plazo.
- `error`: fallo del navegador, selector o flujo; disponibilidad desconocida.

El flujo comienza en `/icpplus/index.html`: provincia, trámite,
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
