# ICPPLUS Monitor

Monitor de citas de extranjería con Selenium, avisos por Telegram y panel en
GitHub Pages. Configurado para Madrid, toma de huellas (inicial, renovación,
duplicado y Ley 14/2013), con alias neutro.

## GitHub Actions y Pages

1. Sube el proyecto a tu repositorio con rama `main`.
2. En **Settings → Secrets and variables → Actions**, crea los secretos
   `TELEGRAM_BOT_TOKEN` (BotFather) y `TELEGRAM_CHAT_ID` (chat destinatario).
   Envía `/start` a tu bot. Nunca guardes el token en Git.
3. En **Settings → Pages → Source**, elige **GitHub Actions**.
4. En **Actions → ICPPLUS Monitor → Run workflow**, inicia una comprobación.
5. En **Actions → Publish dashboard**, consulta la URL del despliegue.

Horario heredado: cada 10 minutos de **06:00 a 12:50 UTC**, y de **22:00 a
22:50 UTC**, diariamente. Está en `.github/workflows/monitor.yml`.
GitHub puede retrasar ejecuciones. El panel recarga resultados cada minuto;
esto no inicia otra comprobación.

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
un perfil; `selectors` permite ajustar selectores. El trámite no ha podido
validarse mientras el portal esté bloqueado.

- `available`: se encontró el calendario; se avisa de posible disponibilidad.
- `unavailable`: hay un mensaje explícito de que no hay citas.
- `blocked`: el portal devuelve 403; disponibilidad desconocida.
- `error`: fallo del navegador, selector o flujo; disponibilidad desconocida.

El flujo heredado puede requerir ajustes cuando el portal sea accesible.
Si exige identificación, CAPTCHA o SMS antes de mostrar disponibilidad,
el proyecto no los completa automáticamente ni puede confirmar citas.
Un bloqueo o una pantalla desconocida no se interpretan como «sin citas».
La reserva se completa manualmente.

`autofill_userscript.js` es un helper opcional para Tampermonkey con datos
ficticios. No publiques datos reales en él. `GMAIL_EMAIL`, `GMAIL_APP_PASSWORD`
y `ALERT_EMAIL_TO` activan también el correo; no hacen falta para Telegram.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
