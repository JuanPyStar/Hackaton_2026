# Uso de inteligencia artificial

Usamos IA como asistente de programación y documentación. Toda la salida se revisó con `./validator check`,
`./validator entregables` y las pruebas del equipo antes de quedar en el repositorio. Abajo, los usos más relevantes y
qué tuvimos que corregir en cada uno.

## Uso 1
- Herramienta: Claude (agente de código con acceso al repositorio)
- Para qué se usó: construir el esqueleto del gateway FastAPI con las 6 rutas, autenticación Bearer y errores `{message, error_id}`
- Prompt principal (resumido): "crea src/ con FastAPI en el puerto 8082, auth por consumidor, health siempre 200 y nombres legacy solo dentro de src/**adapter*"
- Qué produjo: la estructura api/, domain/, services/ y adapter/ con el modelo canónico y el repositorio legacy
- Qué modificó o corrigió el equipo: el modelo de la petición declaraba un campo `date` con el mismo nombre que el tipo `date` de Python y Pydantic lo rechazaba; se cambió a `dt.date`. También exigimos validar el cuerpo después de la autorización para que el token móvil reciba 403 y no 400.

## Uso 2
- Herramienta: Claude
- Para qué se usó: diseñar la resiliencia ante la caída de la base (cortacircuitos, outbox y worker)
- Prompt principal (resumido): "con legacy-db detenida el gateway debe responder 503 en menos de 3 s y los retiros no pueden perderse ni duplicarse"
- Qué produjo: un cortacircuitos que responde 503 sin tocar la base y una primera versión donde el POST también devolvía 503
- Qué modificó o corrigió el equipo: un 503 en el POST pierde el retiro (el incidente de 2023), así que lo cambiamos a 202 con una outbox en un volumen escrita de forma atómica y un worker que reintenta por `requestId`. Lo probamos reiniciando el gateway con la base caída y contando una sola fila RET en LOGMOV.

## Uso 3
- Herramienta: Claude
- Para qué se usó: migrar subsidios-app al gateway conservando el camino legacy para el rollback
- Prompt principal (resumido): "Subsidios debe registrar por el gateway con SUBSIDIOS_TOKEN si Afiliaciones está en DUAL y volver a sp_registrar_retiro en LEGACY, respondiendo igual que hoy"
- Qué produjo: la lectura de config/migration-state.json por petición y la llamada HTTP al gateway
- Qué modificó o corrigió el equipo: un requestId aleatorio por llamada repetía el duplicado de 2021 cuando Subsidios reintenta; lo reemplazamos por un hash estable de documento, fecha y motivo. Además el respaldo al camino legacy solo se activa si la conexión es rechazada, nunca por timeout, para no duplicar.

## Uso 4
- Herramienta: Claude
- Para qué se usó: escribir las pruebas automatizadas del servicio tests con pytest y reporte JUnit
- Prompt principal (resumido): "al menos 10 pruebas contra la API viva, perfil test, JUnit en test-results/"
- Qué produjo: 19 pruebas de salud, autenticación, errores, consultas, retiros, migración y auditoría
- Qué modificó o corrigió el equipo: las primeras pruebas de retiro usaban los afiliados de muestra del validador y los dejaban RETIRED, con lo que G02 fallaba después; ahora escriben sobre un afiliado que ya estaba retirado en los datos y la prueba de auditoría ignora el error_id al buscar documentos.

## Uso 5
- Herramienta: Claude
- Para qué se usó: redactar el mapa de dependencias, el plan de migración y la arquitectura con el formato obligatorio
- Prompt principal (resumido): "llena docs/ con el formato del reto usando procesos.md, el código de los servicios y el procedimiento legacy"
- Qué produjo: las tablas y secciones de los tres documentos
- Qué modificó o corrigió el equipo: quitamos del mapa las filas del portal y del gateway porque el calificador las cuenta como incorrectas, dejando solo las 6 dependencias reales, y pusimos criterios con números medibles ligados al comparador de deriva.

## Uso 6
- Herramienta: Claude
- Para qué se usó: escribir rollback.sh y depurar por qué no leía los tokens del archivo .env
- Prompt principal (resumido): "rollback.sh affiliations debe dejar LEGACY en menos de 3 minutos, verificar /migration/status y terminar en 0"
- Qué produjo: el script con escritura atómica del estado y verificación con curl
- Qué modificó o corrigió el equipo: el .env editado en Windows tenía BOM y finales de línea CRLF, así que la primera variable no se leía; el script ahora los limpia antes de leer y agregamos .gitattributes para forzar LF en los scripts de bash.

## Uso 7
- Herramienta: OpenCode (asistente de código con IA, modelo MiMo)
- Para qué se usó: analizar el kit del evento y extraer las reglas exactas leyendo el código de los validadores del repositorio.
- Prompt principal (resumido): "lee RETO.md, RUBRICA.md y .entregables.py, y dame el estado real de cada entregable GE y cada check G con su requisito exacto"
- Qué produjo: el vault de Obsidian con la tabla de requerimientos verificada contra el calificador (nota 08) y el plan de diez fases ordenado por puntos.
- Qué modificó o corrigió el equipo: verificamos cada regla contra el código del calificador y corregimos el plan inicial, por ejemplo que los merges de git no cuentan, que cada integrante necesita tres commits con su propio correo y que los ADR no aplican a nuestro nivel.

## Uso 8
- Herramienta: OpenCode (asistente de código con IA, modelo MiMo)
- Para qué se usó: dejar el repositorio sano para trabajar: historia de git, protección de secretos y el paquete de documentación que commitea el compañero.
- Prompt principal (resumido): "inicializa git sin subir .env ni la vault, corrige lo que quedó mal al subirlo desde la web de GitHub y prepara tres archivos para que mi compañero haga sus tres commits"
- Qué produjo: la rama main limpia con el kit completo, el .gitignore que excluye .env y el vault, y las primeras versiones de openapi.yaml, docs/architecture.md y AI_USAGE.md validadas al 100 % contra el calificador.
- Qué modificó o corrigió el equipo: reconstruimos la carpeta anidada y los archivos ocultos que se perdieron en la subida manual, confirmamos con git que el .env no entraba al historial y ajustamos después los documentos a la versión final del código.

## Uso 9
- Herramienta: OpenCode (asistente de código con IA, modelo MiMo)
- Para qué se usó: diseñar el video del pitch: guion de seis escenas, textos, tiempos y la animación base en estilo motion graphics.
- Prompt principal (resumido): "prepara el pitch de menos de 60 segundos con los resultados verificados de la bitácora y el demo de caída de la base, en formato horizontal 16:9"
- Qué produjo: docs/pitch/pitch.html con las seis escenas, los textos definitivos y la duración de 55 segundos, más las instrucciones de grano fino para la voz de inteligencia artificial.
- Qué modificó o corrigió el equipo: decidimos motion graphics puro en lugar de terminal grabada, recortamos promesas que el comité no podría verificar y pedimos voz neural con ritmo explicativo tras escuchar una locución inicial robótica.
