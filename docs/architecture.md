# Arquitectura

```text
Portal ─┐
Subsidios ─┼─HTTP+Bearer─▶ Gateway API ─▶ Modelo canónico ─▶ Adapter ─▶ legacy-db ◀── Educación (sin cambios)
App móvil ─┘                 │  auditoría · cortacircuitos · outbox · estado de migración
```

## Contexto

La Caja opera sobre una base legacy (réplica de Informix/Genero) que se volvió el punto de integración de todo:
Educación la lee directamente, Subsidios escribe con `sp_registrar_retiro` y los reportes nocturnos cuentan sobre
`AFI_MAE` y `LOGMOV`. Cambiar una columna rompió tres aplicaciones en 2019, un reintento duplicó retiros en 2021 y una
caída de 40 minutos perdió retiros en 2023. La dirección prohíbe que una aplicación nueva se conecte a la base y no acepta
una migración Big Bang. Por eso construimos una capa de transición que permite migrar dominio por dominio sin apagar el
negocio, empezando por Afiliaciones.

## Componentes

- **gateway** (`src/`, FastAPI, puerto 8082): único servicio nuevo que habla con `legacy-db`. Expone las 6 rutas del
  contrato v1 y `/api/v1/migration/drift`. Capas: `api/` (rutas, autenticación Bearer por consumidor, errores
  `{message, error_id}`), `domain/` (modelo canónico y errores de dominio), `services/` (auditoría, cortacircuitos,
  outbox, estado de migración, deriva) y `adapter/` (único lugar con nombres legacy).
- **Autenticación:** un token por consumidor (`PORTAL_TOKEN`, `SUBSIDIOS_TOKEN`, `MOBILE_TOKEN`); sin token 401 y el
  token móvil recibe 403 en cualquier escritura.
- **Cortacircuitos:** tras una falla de conexión responde 503 `LEGACY_UNAVAILABLE` sin tocar la base durante 5 s, así
  la respuesta llega en milisegundos (contrato: menos de 3 s).
- **Outbox durable + worker:** un retiro recibido con la base caída se guarda en un volumen (`gateway-data`) y se responde
  202; un hilo lo reintenta cada 2 s y lo aplica una sola vez gracias a la idempotencia por `requestId`.
- **Idempotencia transaccional:** en una misma transacción se reserva el `requestId` en `gw_retirement_request`, se
  ejecuta el procedimiento legacy y se guarda el movimiento. Repetir devuelve 200 con la respuesta original.
- **Auditoría:** una línea JSON por petición en `logs/audit.log` (`timestamp`, `consumer`, `endpoint`, `status`,
  `latency_ms`, más `error_id`); todo número de 5+ dígitos se enmascara a 4 visibles.
- **subsidios-app:** lee `config/migration-state.json`; en DUAL/MODERN registra por el gateway, en LEGACY usa el
  procedimiento de siempre. **mobile-app** (8093) es una PWA de solo lectura que consulta por el gateway con el token
  móvil guardado en el servidor. **tests** corre pytest contra la API y deja JUnit en `test-results/`.

## Modelo canónico

Los consumidores solo ven nombres en inglés, estables y sin códigos: `Member {document, fullName, status, company{id,
name}}`, `Beneficiary {document, fullName, relationship}`, `Company {id, name, activeMembers}` y `Retirement {requestId,
document, date, reason, status, movementId}`. El adapter traduce: los nombres y apellidos se unen sin nulos y con un solo
espacio en `fullName`; el estado `A/R/S` pasa a `ACTIVE/RETIRED/SUSPENDED`; el parentesco `C/H/P/M` pasa a
`SPOUSE/CHILD/FATHER/MOTHER` (`OTHER` si llega un código desconocido); `activeMembers` es el conteo de afiliados activos
de la empresa. Ninguna clave legacy aparece en un JSON de respuesta ni en los errores.

## Cambio de esquema

`scripts/schema-change.sh` renombra `AFI_MAE → PERSON_MASTER`, `NRO_DOC → DOCUMENT_NUMBER` y `EST_AFI → STATUS_CODE`.
El adapter tiene dos juegos de nombres (original y renombrado) y detecta el activo con `to_regclass`, lo cachea y, si una
consulta falla por tabla o columna inexistente (el DBA cambió el esquema en caliente), vuelve a detectar y reintenta una
vez. El portal, la app móvil, Subsidios y el contrato no cambian: probamos que el validador da el mismo resultado antes y
después del script, que los retiros siguen funcionando y que el comparador de deriva sigue en 0 diferencias.

## Alternativas descartadas

- **Migración Big Bang a una base nueva:** exige apagar el negocio y reescribir Educación, que no se puede modificar; el
  rollback sería restaurar un respaldo completo. Se descartó por riesgo y porque la dirección no la acepta.
- **Vistas SQL con los nombres viejos para absorber el cambio de esquema:** esconde el problema dentro de la base, sigue
  acoplando a cada consumidor con tablas y columnas, y no da autenticación, auditoría ni idempotencia.
- **Reintentos automáticos en Subsidios sin idempotencia:** es exactamente lo que duplicó retiros en 2021; preferimos un
  `requestId` estable y una tabla de idempotencia en la misma transacción.
- **Cola externa (RabbitMQ/Kafka) para la outbox:** suma un servicio que también puede caerse y más configuración; un
  archivo atómico en un volumen más idempotencia en la base cubre el caso con menos piezas.
