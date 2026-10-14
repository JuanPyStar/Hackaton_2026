# 04 · Arquitectura propuesta

> [!summary] Patrones: **Anti-Corruption Layer + Strangler Fig + Outbox**. Eso es lo que se cuenta en el pitch.

## Estructura de código

```text
src/
├── app.py                    FastAPI + uvicorn (:8082)
├── adapter/                  ← ÚNICO lugar con nombres legacy
│   ├── legacy_repository.py  SQL; detección dual de esquema (afi_mae / person_master)
│   ├── idempotency_store.py  requestId → resultado (transaccional con el SP)
│   └── outbox.py             retiros aceptados en caída (aplicar 1 sola vez)
├── domain/                   modelo canónico: Member, Beneficiary, Company, Retirement
├── api/                      rutas, auth Bearer, errores {message, error_id}
└── services/                 circuit breaker, auditoría (masking), worker de replay

config/migration-state.json   estado LEGACY|DUAL|MODERN (montado en gateway y subsidios)
logs/audit.log                1 JSON por petición (montado en el host)
test-results/                 reporte JUnit del servicio tests
tests/                        pytest contra la API viva
```

> [!important] Regla GE01
> `AFI_MAE`, `NRO_DOC`, `EST_AFI`, `LOGMOV`, `sp_registrar_retiro`, `person_master`, `DOCUMENT_NUMBER`, `STATUS_CODE`… solo dentro de carpetas/archivos con **"adapter"** en el nombre — **ni siquiera en comentarios** fuera de `src/adapter/`.

## Composición del docker-compose (lo que se agrega)

```yaml
  gateway:
    build: ./src
    env_file: .env
    ports: ["8082:8082"]
    volumes:
      - ./logs:/app/logs
      - ./config:/app/config
    depends_on:
      legacy-db: { condition: service_healthy }

  mobile-app:                # evento 3: nuevo consumidor, SIN tocar la base
    build: ./services/mobile
    env_file: .env
    ports: ["8093:8093"]

  tests:
    build: ./tests
    env_file: .env
    profiles: ["test"]
    volumes:
      - ./test-results:/app/test-results
```

Solo `gateway…`, `adapter…` y `tests` pueden conectarse a `legacy-db`. `mobile-app` y `tests` van **solo por HTTP**.

## Los 6 mecanismos que ganan los puntos

### 1. Detección dual de esquema (G09 = 60 pts)
El adapter resuelve los nombres al arrancar (mismo truco que `educacion-app`: intenta la consulta nueva y si falla con `UndefinedTable` usa la vieja, o viceversa). Cachea el esquema activo. **El gateway jamás cambia.**

### 2. Idempotencia transaccional (G08 = 40 pts)
En **una sola transacción** contra la DB: verificar `requestId` → llamar `sp_registrar_retiro` → guardar `requestId`. Exactamente-una-vez atómico. Repetición → `200` con la respuesta original.

### 3. Circuit breaker + 503 rápido (G10 = 50 pts)
- `connect_timeout=2`, `statement_timeout` corto.
- Al primer fallo, breaker abierto → responder `503 {"code":"LEGACY_UNAVAILABLE"}` de inmediato (**sin tocar la DB**, garantiza <3 s).
- `/health` sigue en `200` con `legacy: "DOWN"`.

### 4. Outbox durable (G11 = 50 pts)
- `POST /retirements` con legacy caído → `202` + append a un archivo local montado (`./logs/outbox.jsonl` o `./config/…`) — **persiste reinicios**.
- Worker en background: al detectar DB arriba, reejecuta **por `requestId`** → el mecanismo 2 evita duplicados. Pasa también cuando el request viene de subsidios.

### 5. Estado de migración compartido (G14, GE04)
- `config/migration-state.json` montado en `gateway` y `subsidios-app` (ambos lo leen por petición → sin reinicios raros).
- `rollback.sh affiliations`: escribe `LEGACY` → verifica `/migration/status` → asegura que subsidios usa el camino legacy → imprime estado → código 0 en segundos.
- `subsidios-app`: si estado = DUAL/MODERN → gateway con `SUBSIDIOS_TOKEN` + `requestId`; si LEGACY → `sp_registrar_retiro` directo. **Respuesta actual intacta** (`201 {"movimiento": N}`).

### 6. Auditoría + observabilidad (G12, G06)
- Middleware que loguea **todas** las peticiones (incluye `/health`) en `logs/audit.log`: `timestamp, consumer, endpoint, status, latency_ms`.
- `consumer` = token usado (`portal`/`subsidios`/`mobile`; sin token → valor neutro).
- Documento **siempre enmascarado**: máx. 4 dígitos visibles (ej. `****2447`). Nunca el documento completo.
- `error_id` único en cada error, correlacionado con la línea de auditoría (trazabilidad real).

## Modelo canónico (mapeos)

| Legacy | Canónico |
|---|---|
| `nom1 nom2 ape1 ape2` | `fullName` (sin nulos, un espacio) |
| `est_afi` A/R/S | `status` ACTIVE/RETIRED/SUSPENDED |
| `cod_emp` / `nom_emp` | `company.id` / `company.name` |
| `cod_par` C/H/P/M | `relationship` SPOUSE/CHILD/FATHER/MOTHER (documentar en architecture.md) |
| conteo afiliados `A` por empresa | `activeMembers` |

## Stack

Python 3.12 + FastAPI + uvicorn + psycopg2-binary (mismo lenguaje que el kit); pytest + `pytest --junitxml` para el servicio `tests`. Se puede generar `openapi.yaml` desde FastAPI y ajustarlo.
