# Diagnóstico de acceso desde GitHub Actions

Prueba realizada el 25 de octubre de 2026 desde un runner `ubuntu-latest`
en Azure `eastus2`. No se cargaron secretos ni se introdujeron datos del
solicitante durante el diagnóstico.

## Resultados medidos

| Comprobación | Resultado |
| --- | --- |
| DNS del portal | `185.73.174.73`, respuesta en 0,094 s |
| HTTPS de control a GitHub.com | HTTP 200 en 0,068 s |
| TCP al portal, puerto 443 | No se establece conexión en 12 s |
| Negociación TLS con el portal | No llega a comenzar |
| Respuesta HTTP del portal | Ninguna; código HTTP 0 en curl |
| Repetición con HTTP/1.1 | Mismo timeout de conexión TCP |
| Chrome 156 con ChromeDriver 156, sin ventana | Timeout de navegación en 30 s; sin documento |
| Chrome 156 con ChromeDriver 156, con ventana mediante Xvfb | Mismo resultado |
| Monitor con versiones emparejadas | Timeout inicial en 60 s, antes de identificar al solicitante |

Fuentes reproducibles:

- [Ejecución del diagnóstico y report.json](https://github.com/iAlexX-16/icpplus-monitor/actions/runs/40151091268)
- [Ejecución del monitor corregido](https://github.com/iAlexX-16/icpplus-monitor/actions/runs/40151091247)

## Interpretación

El fallo observado ocurre al establecer la conexión de red TCP desde el
runner al servidor del portal. Al no comenzar TLS ni recibirse HTTP, en esta
prueba no intervienen el contenido de la página, los selectores, el NIE o
el CAPTCHA. También se reproduce con curl y con un navegador con ventana.

Es compatible con un filtrado de las direcciones de salida de centros de
datos o con un problema de ruta entre Azure y la red del portal. Las pruebas
no permiten atribuir el filtrado a una parte concreta ni afirmar una regla
geográfica: harían falta registros de los operadores de red o del servidor.
El acceso manual usa otra conexión de origen y puede funcionar a la vez.

Se corrigió además una instalación redundante: se instalaba Chrome 156,
pero se terminaba usando Chrome y ChromeDriver 155. Ahora el monitor usa
explícitamente los dos binarios compatibles instalados por la misma acción.
La prueba posterior sigue mostrando el fallo de conectividad.

## Funcionamiento configurado

El monitor se trasladó a Windows cada quince minutos. Actualmente solo se
ejecuta al abrir **ICPPLUS Monitor** y pulsar **Iniciar**; cerrar la ventana
detiene los procesos de consulta. La tarea de Windows anterior está desactivada. La
ejecución automática de Azure se desactivó para no duplicar comprobaciones.
El equipo debe permanecer encendido, despierto y con la sesión iniciada.

Mientras la conexión falle, el resultado es `error`, sin afirmar que no hay
citas. Aumentar el timeout prolongaría la espera sin restablecer la conexión.
La solución local no instala un runner de GitHub ni un servicio de acceso
remoto. El resultado se publica desde el propio equipo con Git Credential
Manager y sin datos de identidad.

## Validación local posterior

Se corrigió la entrada pública a `/icpplus/index.html`: iniciar directamente
en `/icpplustiem/index.html` daba una página vacía para una sesión nueva en
la prueba local. Esto no altera el diagnóstico TCP de Azure, que fallaba
antes de solicitar cualquier ruta HTTP.

El 25 de octubre de 2026 a las 01:50:14 UTC, una consulta desde Chrome visible
con un perfil propio y persistente completó provincia, trámite, identificación
y solicitud de disponibilidad. Encontró un mensaje explícito de ausencia
de citas. Otras consultas recibieron `Request Rejected` después de la
selección de provincia: el acceso local puede ser intermitente y los
rechazos se mantienen como estado `blocked`.

Se conserva la sesión en un perfil dedicado, se vuelve a renderizar el
formulario si contiene identificadores de sesión en la URL y se termina
la sesión mediante `Salir` cuando el portal ofrece esa opción. Nunca se
selecciona una fecha ni se confirma una reserva.

La validación final desde el Programador de tareas, a las 02:04:35 UTC,
completó de nuevo la consulta y encontró ausencia de citas. La tarea terminó
con código 0, publicó el resultado anonimizado en GitHub y el panel reflejó
ese estado. En aquella prueba la tarea estaba habilitada con repetición `PT15M`
y evitaba instancias simultáneas. Telegram también se verificó desde la configuración local cifrada.

## Revisión de horario y acceso denegado

La revisión posterior del registro encontró 147 consultas completas de
ausencia de citas y un `Request Rejected` a las 15:18 (Europe/Madrid), tras
seleccionar provincia. El rechazo corresponde al portal; no hay un error
de permisos de Windows en ese registro. La siguiente consulta a las 15:23
volvió a completarse. Sin registros del servidor no se puede atribuir con
certeza el rechazo a una regla concreta; no implica un bloqueo permanente.

Se corrigió que un rechazo pudiera terminar con código 0. Ahora una consulta
fallida conserva y publica su estado de error y termina con código no cero.
Antes de enviar datos de identidad se permite un único reinicio de la sesión
del perfil exclusivo del monitor, si aún quedan al menos 35 segundos hasta
el objetivo. No se reintenta CAPTCHA ni un 403.

La tarea prepara a :14, :29, :44 y :59 y espera al próximo cuarto de hora.
En la prueba real de las 15:30, quedó preparada a las 15:29:33.792, inició
el envío a las 15:30:00.000 y envió la petición posterior de disponibilidad
a las 15:30:00.212. El portal respondió explícitamente que no había citas.
Estos tiempos son del ordenador, no una garantía del instante de procesado
en el servidor. Si se pierde el objetivo por más de un segundo, no se consulta
fuera de plazo.

El diagnóstico puede repetirse en Actions, con el workflow
`Diagnose ICPPLUS connection`. Solo hace solicitudes anónimas acotadas y
el informe elimina parámetros y sesiones de las URL.

## Rechazo de las 02:00 del 26 de octubre de 2026

La preparación comenzó a las 01:59:00 (Europe/Madrid). A las 01:59:30,
tras aceptar el trámite, el portal rechazó `/icpplustiem/acInfo`. No se
habían introducido datos del solicitante ni solicitado disponibilidad.
Quedaban 30 segundos para el objetivo: el mínimo de 35 segundos para un
único reintento no se cumplía. El estado `blocked` se publicó correctamente.
Los tiempos entre corchetes del registro anterior estaban en UTC; desde
esta revisión incluyen la indicación `UTC` para evitar confusiones.

Dos pruebas públicas sin identificación reprodujeron el mismo rechazo,
una con el perfil del monitor y otra con un perfil temporal vacío. La
respuesta fue HTTP 200 con el título `Request Rejected`, no un timeout ni
un 403. La página mostraba un Support ID de la protección del portal.
Este formato se documenta en [F5](https://my.f5.com/manage/s/article/K000146818):
el administrador puede consultar la regla exacta mediante ese identificador.

El formulario de selección del trámite contenía `;jsessionid=…` en sus
acciones, incluso después de haber inicializado la sesión de la portada.
La portada `/icpplus` y el trámite `/icpplustiem` establecen contextos de
sesión distintos. Una recarga normal del formulario del trámite, después
de recibir su cookie de sesión, eliminó el identificador de las acciones
y permitió avanzar a la identificación, sin enviar datos personales.
El monitor incorpora ahora esa misma recarga condicional una sola vez,
antes de seleccionar el trámite. No cambia los parámetros del formulario,
las protecciones del navegador ni el horario de consulta.

Las pruebas apuntan a la inicialización de la sesión y a las URL del
formulario como desencadenante reproducible; no prueban qué regla interna
aplicó el portal ni garantizan que no vuelva a rechazar otra petición.
Los futuros rechazos guardan el Support ID numérico en el resultado y
registro locales, sin capturas ni HTML de páginas con identidad. Ese
identificador no se publica en el panel.

La prueba del código corregido, a las 02:07 del 26 de octubre, alcanzó de
nuevo el formulario de identificación sin rechazo. Se detuvo allí sin
introducir datos ni consultar disponibilidad; no sustituye al estado de
la consulta de las 02:00. Pasaron las 33 pruebas locales, incluida la
inicialización del formulario del trámite y la omisión del reintento
cuando solo quedan 30 segundos.
