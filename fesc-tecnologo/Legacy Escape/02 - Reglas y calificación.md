# 02 · Reglas y calificación

> [!info] Fórmula
> `nota = (puntos_validador / 500) × 70 + entregables (sobre 30) − penalizaciones`, entre 0 y 100.

## Validador — 15 pruebas (500 pts → 70)

| ID | Prueba | Qué se verifica | Pts | Dónde corre |
|---|---|---|---:|---|
| G01 | Salud | `GET /health` → 200 con estado del legacy | 10 | público |
| G02 | Afiliado | Datos correctos y sin nombres de columnas legacy en el JSON | 40 | público |
| G03 | Beneficiarios | Lista correcta para una muestra **oculta** | 30 | público (estructura) / oficial (datos) |
| G04 | Empresa | Datos y `activeMembers` correctos | 20 | público (estructura) / oficial (valor) |
| G05 | Auth y privilegios | Sin token → 401; `MOBILE_TOKEN` lee → 200, escribe → 403 | 40 | público |
| G06 | Errores | 404 con `{message, error_id}`; sin trazas ni SQL | 10 | público |
| G07 | Retiro migrado | `POST .../retirements` → 201 y visible en la base legacy (y para Educación) | 60 | **solo oficial** |
| G08 | Idempotencia | Mismo `requestId` → 200, **una sola** fila en `LOGMOV` | 40 | **solo oficial** |
| G09 | Cambio de esquema | Tras `schema-change.sh`, G02–G04 responden idéntico | 60 | **solo oficial** |
| G10 | Legacy caído | Con la base detenida: 503 `LEGACY_UNAVAILABLE` en <3 s | 50 | **solo oficial** |
| G11 | Retiro en caída | Ningún retiro aceptado se pierde ni duplica al recuperar | 50 | **solo oficial** |
| G12 | Auditoría | `logs/audit.log` con los 5 campos y documento enmascarado | 30 | público |
| G13 | Reversibilidad | `sp_registrar_retiro` sigue existiendo | 20 | público |
| G14 | Estado de migración | `/migration/status` coherente con `migration-plan.md` | 10 | público |
| G15 | Subsidios migrado | `POST :8091/retiros` pasa por el gateway: audit `consumer=subsidios` y una sola fila en `LOGMOV` | 30 | **solo oficial** |

Los oficiales (G07–G11, G15) se prueban **a mano** con `./reset.sh` de por medio. Ver comandos en [[05 - Plan de desarrollo]].

## Entregables (30 pts)

| ID | Entregable | Qué revisa | Pts |
|---|---|---|---:|
| GE01 | Adapter encapsula el esquema | Nombres legacy solo en `src/**/adapter*`; puntaje = adapter / todos los archivos de `src/` que los nombran | 5 |
| GE02 | Mapa de dependencias | Tabla comparada con **6 dependencias reales**; filas incorrectas **restan** | 3 |
| GE03 | Plan de migración | ≥3 dominios (incl. Afiliaciones), estados válidos, criterios con número medible, rollback por fila y línea `Siguiente dominio:` | 3 |
| GE04 | Rollback ejecutable | `./rollback.sh affiliations` sin error → estado `LEGACY` y retiro desde Subsidios sigue en la base | 3 |
| GE05 | Pruebas automatizadas | `docker compose --profile test run --rm tests` sin fallas + JUnit en `test-results/` con **≥10 pruebas** | 3 |
| GE06 | OpenAPI | `openapi.yaml` OpenAPI 3 con las 6 rutas | 2 |
| GE07 | Arquitectura | 5 secciones (Contexto, Componentes, Modelo canónico, Cambio de esquema, Alternativas descartadas), ≥20 palabras c/u, ≥2 alternativas en lista | 1 |
| GE08 | Historial Git | ≥10 commits, ≥3 por integrante, mensajes descriptivos | 1 |
| GE09 | IA documentada | `AI_USAGE.md` con ≥3 usos completos | 2 |
| GE10 | Pitch | Video **≤60 s**, Drive público, registrado antes del cierre y sin modificar después (mitad sistema + mitad comité) | 5 |
| GE11 | README | 11 secciones contrastadas con `.env.example`, `docker-compose.yml`, contrato y comandos | 2 |

## Detalles "internos" del validador (descifrados del código)

- **Documentos de prueba (G02/G12):** `1019282447` → "IVAN HERNANDEZ GARCIA", empresa `2014`; `6039066119` → "RICARDO VARGAS QUINTERO", empresa `2014`. Inexistente: `0000000001`. La empresa `2014` es "AGROPECUARIA SANTANDER SA".
- **G02 compara huellas (hash con sal):** debe coincidir exactamente `documento | NOMBRE COMPLETO EN MAYÚSCULAS | status | id empresa | NOMBRE EMPRESA EN MAYÚSCULAS`. `fullName` = nombres + apellidos unidos con un espacio, sin nulos.
- **Claves JSON prohibidas (G02):** ninguna clave puede ser (en mayúsculas) `NRO_DOC, NOM1, NOM2, APE1, APE2, EST_AFI, COD_EMP, NOM_EMP, COD_PAR, NRO_DOC_BEN, DOCUMENT_NUMBER, STATUS_CODE`.
- **G06:** el cuerpo del error no puede contener `Traceback`, `Exception`, `SELECT`, `afi_mae`, `nro_doc`, `psycopg`.
- **G12:** revisa las **últimas 200 líneas** de `logs/audit.log`; todas deben tener los 5 campos y **el documento completo de los 2 miembros no puede aparecer** en ninguna línea.
- **GE02 — las 6 dependencias exactas** (de `docs/procesos.md`):

  | Aplicación | Tabla | Operación | Criticidad |
  |---|---|---|---|
  | Educación | AFI_MAE | Lectura | Alta |
  | Educación | EMPRESA | Lectura | Media |
  | Subsidios | AFI_MAE | Escritura | Alta |
  | Subsidios | LOGMOV | Escritura | Media |
  | Reportes nocturnos | AFI_MAE | Lectura | Media |
  | Reportes nocturnos | LOGMOV | Lectura | Baja |

  ⚠️ **No agregar filas de Portal, Móvil, gateway ni adapter**: las que no estén en esa lista de 6 restan (cero filas de más). `Criticidad` debe ser Alta/Media/Baja (20 % de la nota de GE02).
- **GE01:** se escanea todo `src/` (excepto tests). Si un archivo fuera del adapter nombrado `AFI_MAE` etc., el puntaje es `adapter / (adapter + fuera)`. Un solo archivo fuera ya descuenta.
- **GE08:** mensajes genéricos rechazados: `update, fix, wip, cambios, avance, ok, listo, test…`. Ejemplo bueno: "corrige host de la base en cierre-api".

## Reglas comunes (penalizaciones y descalificaciones)

| Situación | Efecto |
|---|---|
| Repo no registrado o no público al cierre | **NO CALIFICADO** |
| Sin commits antes de la hora límite | **NO CALIFICADO** |
| `.env` (o su valor) en el historial u otro archivo | −5 |
| `AI_USAGE.md` ausente o sin uso completo | −5 |
| Servicio nuevo (no `gateway*`/`adapter*`/`tests`) conectado a `legacy-db` | −10 y 0 en GE01 |
| `docker compose up` falla o `compose` usa `privileged`/`cap_add`/`devices`/red del host/montajes fuera del repo | validador = 0 |
| Copia entre equipos (≥60 % de líneas comunes) | descalificación |
| Documento entregado en .docx/.pdf en vez de .md, o archivo >1 MB | entregable vale 0 |

## Git y entrega

- Ambos integrantes commitean con **su nombre y correo**: mínimo **10 commits**, **≥3 de cada uno**, mensajes que describan el cambio.
- Se califica el **último commit anterior a la hora límite**.
- Levantable desde cero con `docker compose up -d --build`; scripts con `bash` y solo `docker/compose, git, python3, curl, jq, psql` + utilidades estándar.
- Secretos en `.env` (no versionado) + `.env.example` entregado.
- **README = 11 secciones obligatorias**: Descripción, Integrantes, Requisitos y ejecución, Configuración, Arquitectura, Uso, Pruebas, Documentación, Qué resolvimos, Limitaciones y pendientes. Contrasta: Configuración ↔ cada variable de `.env.example`; Arquitectura ↔ cada servicio del compose; Uso ↔ las 6 rutas; Pruebas ↔ `docker compose --profile test run --rm tests`; Documentación ↔ enlaces a los entregables.
- **Pitch:** video ≤60 s en Drive ("Cualquier persona con el enlace"), registrado en **Mi equipo** antes del cierre; no tocarlo después.

## Premios

| Premio | Para |
|---|---|
| **Product Builder** | Mayor nota final del nivel Tecnólogo ← **nuestro objetivo principal** |
| **AI Engineering Award** | Mejor `AI_USAGE.md` entre equipos sin penalizaciones |
| **FESC Productization** | Top 3 con sin penalizaciones + validador ≥80 % + entregables ≥80 % |

Desempate: 1) mayor validador, 2) mayor entregables, 3) commit final más temprano.
