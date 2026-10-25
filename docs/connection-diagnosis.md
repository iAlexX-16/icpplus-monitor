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

El monitor está programado cada cinco minutos, las 24 horas, mediante
`*/5 * * * *`. GitHub puede retrasar o descartar ejecuciones programadas;
el intervalo no es una garantía de puntualidad.

Mientras la conexión falle, el resultado es `error`, sin afirmar que no hay
citas. Aumentar el timeout prolongaría la espera sin restablecer la conexión.
Para obtener consultas reales se necesita un entorno con acceso al portal,
por ejemplo un equipo propio en una red que permita abrirlo. La instalación
de un runner propio es un cambio adicional que requiere elegir y autorizar
ese equipo; este trabajo no instala ningún servicio local de acceso remoto.

El diagnóstico puede repetirse en Actions, con el workflow
`Diagnose ICPPLUS connection`. Solo hace solicitudes anónimas acotadas y
el informe elimina parámetros y sesiones de las URL.
