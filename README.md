# Legacy Escape — Gateway de Afiliaciones

Reto Tecnólogo del FESC Legacy Challenge 2026: modernizar el sistema legacy de una Caja de Compensación **sin apagarlo**.

## Descripción

Construimos la capa de transición que permite a la Caja migrar el dominio **Afiliaciones** sin una migración Big Bang:
un gateway REST con modelo canónico y un adapter que es el único que conoce la base legacy. El portal, Subsidios y una
nueva app móvil consultan y registran retiros por la API; Educación sigue leyendo la base sin cambios. El sistema resiste
el cambio de esquema del DBA y la caída de la base (ningún retiro se pierde ni se duplica), audita cada petición con los
documentos enmascarados y se puede revertir a LEGACY con un solo comando.

## Integrantes

- Juan David — gateway, adapter, resiliencia, migración de Subsidios, rollback y despliegue
- Andres Mendez — app móvil, pruebas automatizadas, contrato OpenAPI, arquitectura y documentación de uso de IA

## Requisitos

- Docker Engine 24+ con Docker Compose v2 (en Windows, Docker Desktop con WSL 2).
- `bash`, `curl` y `python3` en el host para `./rollback.sh`, `./reset.sh` y `./validator` (en Windows: Git Bash).
- Puertos libres: 8082 (gateway), 8090 (Educación), 8091 (Subsidios), 8092 (portal), 8093 (app móvil).

## Instalación y ejecución

Desde una copia limpia del repositorio:

```bash
cp .env.example .env              # y cambie las claves y los tres tokens por valores propios
docker compose up -d --build      # levanta legacy-db, gateway, consumidores y app móvil
docker compose ps                 # todos arriba; gateway y legacy-db en (healthy)
./validator check                 # pruebas públicas del contrato
docker compose --profile test run --rm tests   # pruebas del equipo (JUnit en test-results/)
./rollback.sh affiliations        # si hace falta: devuelve Afiliaciones a LEGACY
./scripts/set-migration-state.sh affiliations DUAL   # volver a avanzar el dominio
./reset.sh                        # estado inicial (borra contenedores y volúmenes)
```

## Configuración

Todas las variables viven en `.env` (no se versiona); `.env.example` trae valores de ejemplo.

| Variable | Para qué sirve | Ejemplo |
|---|---|---|
| `POSTGRES_DB` | Nombre de la base legacy | `legacy` |
| `POSTGRES_USER` | Usuario de la base legacy (lo usan legacy-db, gateway, Educación y Subsidios) | `legacy` |
| `POSTGRES_PASSWORD` | Clave de ese usuario | `cambiar-esta-clave` |
| `LEGACY_DB_HOST` | Host de la base dentro de la red de Docker (nombre del servicio) | `legacy-db` |
| `LEGACY_DB_PORT` | Puerto de PostgreSQL | `5432` |
| `GATEWAY_URL` | URL interna del gateway que usan el portal, Subsidios y la app móvil | `http://gateway:8082` |
| `PORTAL_TOKEN` | Token Bearer del portal (lectura y escritura) | `cambiar-portal` |
| `SUBSIDIOS_TOKEN` | Token Bearer de Subsidios (lectura y escritura; su consumidor en la auditoría es `subsidios`) | `cambiar-subsidios` |
| `MOBILE_TOKEN` | Token Bearer de la app móvil (solo lectura: un POST recibe 403) | `cambiar-mobile` |

Opcionales del gateway (tienen valor por defecto): `BREAKER_OPEN_SECONDS` (5), `OUTBOX_INTERVAL_SECONDS` (2),
`LEGACY_CONNECT_TIMEOUT` (2), `LEGACY_CALL_TIMEOUT_SECONDS` (2, plazo máximo por llamada a la base), `EDUCACION_URL` (`http://educacion-app:8090`).

## Arquitectura

```text
portal-client ─┐
subsidios-app ─┼─ HTTP + Bearer ─▶ gateway (8082) ─▶ modelo canónico ─▶ adapter ─▶ legacy-db ◀── educacion-app
mobile-app ────┘
```

- **legacy-db**: PostgreSQL 16 con el esquema heredado (AFI_MAE, AFI_BEN, EMPRESA, APORTES, LOGMOV) y `sp_registrar_retiro`.
- **gateway**: FastAPI en `src/`. Único servicio nuevo que se conecta a legacy-db. Autenticación por consumidor, errores
  `{message, error_id}`, auditoría en `logs/audit.log`, cortacircuitos (503 en milisegundos), outbox durable con worker
  (202 durante la caída, aplicado una sola vez), idempotencia transaccional por `requestId`, detección doble de esquema y
  comparador de deriva. Los nombres legacy solo existen en `src/adapter/`.
- **educacion-app**: aplicación legacy que lee la base directo; no se modificó.
- **portal-client**: portal que solo habla con `GATEWAY_URL`; no se modificó.
- **subsidios-app**: registra retiros; lee `config/migration-state.json` en cada petición: en DUAL/MODERN usa el gateway con
  `SUBSIDIOS_TOKEN` y un `requestId` estable; en LEGACY vuelve a `sp_registrar_retiro`.
- **mobile-app**: PWA de consulta (8093) para el evento 3; solo HTTP al gateway con `MOBILE_TOKEN`, sin acceso a la base.
- **tests**: perfil `test`; pytest contra la API en funcionamiento, reporte JUnit en `test-results/`.

Detalle en [docs/architecture.md](docs/architecture.md).

## Uso

Todas las rutas (salvo `/health`) piden `Authorization: Bearer <token>`.

| Método y ruta | Qué devuelve |
|---|---|
| `GET /health` | `200 {status, legacy, pendingRetirements}` siempre, aunque la base esté caída |
| `GET /api/v1/members/{document}` | Afiliado: `document`, `fullName`, `status` (ACTIVE/RETIRED/SUSPENDED), `company {id, name}` |
| `GET /api/v1/members/{document}/beneficiaries` | Lista de `{document, fullName, relationship}` |
| `GET /api/v1/companies/{id}` | `{id, name, activeMembers}` |
| `POST /api/v1/members/{document}/retirements` | Cuerpo `{requestId, date, reason}` → 201; mismo `requestId` → 200; base caída → 202 |
| `GET /api/v1/migration/status` | `{domains: {affiliations: LEGACY/DUAL/MODERN, ...}}` |
| `GET /api/v1/migration/drift?sample=50` | Comparador de deriva gateway vs. Educación |

Ejemplos:

```bash
T="Authorization: Bearer $PORTAL_TOKEN"
curl http://localhost:8082/health
# {"status":"UP","legacy":"UP","pendingRetirements":0}

curl -H "$T" http://localhost:8082/api/v1/members/1019282447
# {"document":"1019282447","fullName":"IVAN HERNANDEZ GARCIA","status":"ACTIVE","company":{"id":"2014","name":"AGROPECUARIA SANTANDER SA"}}

curl -H "$T" http://localhost:8082/api/v1/members/1019282447/beneficiaries
# [{"document":"1112049023","fullName":"CLAUDIA JOSE PARRA MOLINA","relationship":"SPOUSE"}]

curl -H "$T" http://localhost:8082/api/v1/companies/2014
# {"id":"2014","name":"AGROPECUARIA SANTANDER SA","activeMembers":17}

curl -X POST -H "$T" -H "Content-Type: application/json" \
  -d '{"requestId":"demo-1","date":"2026-10-05","reason":"voluntario"}' \
  http://localhost:8082/api/v1/members/1019282447/retirements
# 201 la primera vez · 200 con la misma respuesta si se repite demo-1 · 202 si la base está caída

curl -H "$T" http://localhost:8082/api/v1/migration/status
# {"domains":{"affiliations":"DUAL","contributions":"LEGACY","reports":"LEGACY"}}

curl -H "$T" "http://localhost:8082/api/v1/migration/drift?sample=50"
# {"checked":50,"differences":0,...}   gateway vs. lo que ve Educación
```

App móvil: abrir `http://localhost:8093` en el teléfono o el navegador. Subsidios sigue igual:
`curl -X POST localhost:8091/retiros -H 'Content-Type: application/json' -d '{"documento":"1019282447","fecha":"2026-10-05","motivo":"voluntario"}'`.

## Pruebas

```bash
docker compose --profile test run --rm tests
```

El servicio `tests` ejecuta 19 pruebas pytest contra el gateway en funcionamiento (solo HTTP) y deja el reporte JUnit en
`test-results/junit.xml`; termina con código distinto de 0 si alguna falla. Cubren: salud, 401 sin token o con token
inválido, lectura móvil 200 y escritura móvil 403, afiliado en modelo canónico sin columnas legacy, 404 y 400 con
`{message, error_id}` sin trazas ni SQL, beneficiarios, empresa con `activeMembers`, retiro 201 y repetición 200 con el
mismo movimiento, `requestId` reutilizado para otro afiliado (409), estado de migración, comparador de deriva en 0 y
auditoría con los 5 campos y documentos enmascarados. Las escrituras usan un afiliado que ya estaba retirado para no
alterar los datos que revisa el validador.

## Documentación

- [docs/architecture.md](docs/architecture.md) — contexto, componentes, modelo canónico, cambio de esquema y alternativas descartadas.
- [docs/dependency-map.md](docs/dependency-map.md) — quién lee y quién escribe cada tabla legacy.
- [docs/migration-plan.md](docs/migration-plan.md) — dominios, estados LEGACY/DUAL/MODERN, criterios y rollback.
- [openapi.yaml](openapi.yaml) — contrato v1 (OpenAPI 3).
- [AI_USAGE.md](AI_USAGE.md) — cómo usamos la IA y qué corregimos.

## Qué resolvimos

Las aplicaciones nuevas ya no conocen la base: el portal, Subsidios y la app móvil hablan con un contrato estable y el
adapter absorbe el cambio de esquema del DBA (el validador da lo mismo antes y después). Los incidentes históricos quedaron
cubiertos: el duplicado de 2021 por idempotencia transaccional y `requestId` estable en Subsidios; la pérdida de retiros
de 2023 por la outbox durable que aplica una sola vez al volver la base, incluso si el gateway se reinicia durante la
caída; la exposición de documentos de 2025 por la auditoría enmascarada. El dominio Afiliaciones está en DUAL con un
comparador de deriva que mide el criterio para avanzar y un rollback de un comando que tarda menos de un segundo.

## Limitaciones y pendientes

- La outbox es un archivo en un volumen de un solo gateway; con varias réplicas habría que moverla a una tabla o cola compartida.
- Educación y los reportes nocturnos siguen leyendo la base directamente (Educación no se puede modificar), por eso
  Afiliaciones no puede pasar a MODERN todavía.
- Si una petición llega a una base caída y el afiliado no existe, se acepta con 202 y luego queda en
  `outbox-dead.jsonl` del volumen; falta notificar ese caso al consumidor.
- Los dominios Aportes y Reportes siguen en LEGACY; el siguiente es Aportes.
