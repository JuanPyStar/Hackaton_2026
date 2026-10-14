# 01 · Análisis del reto — Legacy Escape (nivel Tecnólogo)

> [!summary] En una frase
> Construir la **capa de transición** (Gateway API + Adapter + modelo canónico) y migrar el dominio **Afiliaciones** sin apagar el negocio, bajo la política: *ninguna aplicación nueva puede conectarse directamente a la base legacy*.

## Escenario

Una Caja de Compensación Familiar lleva años sobre un sistema legacy (IBM Informix/Genero) cuya base de datos es el punto de integración de todo: afiliaciones, subsidios, educación, reportes. Cambiar una columna rompe aplicaciones y validar afiliaciones con otras cajas es manual.

No existe migración Big Bang: el sistema **debe seguir operando** mientras se migra dominio por dominio.

## Misión

```text
Portal / Subsidios / Móvil → Gateway API (:8082) → Modelo canónico → Adapter → Legacy DB
                                                          Educación sigue leyendo directo (NO se modifica)
```

1. **Discovery** — mapa de quién lee, quién escribe y qué tablas toca cada aplicación.
2. **Consultas por API** — el portal funciona sin conocer tablas, columnas ni códigos.
3. **Escritura migrada** — el retiro se registra por el servicio nuevo y queda en la base legacy, de modo que Educación y los reportes viejos lo ven.
4. **Reversibilidad** — si se desactiva el servicio nuevo, el camino legacy (`sp_registrar_retiro`) sigue funcionando y `./rollback.sh affiliations` devuelve el dominio a LEGACY.
5. **Plan de migración** por dominio con estados `LEGACY → DUAL → MODERN`, criterios medibles y mecanismo de rollback.

## Consumidores

| Aplicación | Qué hace | ¿Se puede modificar? |
|---|---|---|
| `educacion-app` (:8090) | Lee afiliados directo de la base | **No** |
| `portal-client` (:8092) | Consulta afiliados, beneficiarios, empresas | **No**: solo configura `GATEWAY_URL` |
| `subsidios-app` (:8091) | Registra retiros de afiliados | **Sí**: debe pasar a registrarlo por el gateway con `SUBSIDIOS_TOKEN` (conservar camino legacy para rollback) |
| App móvil (nueva) | Consulta afiliados y beneficiarios | Se construye durante el reto (solo lectura con `MOBILE_TOKEN`) |

## Los 3 eventos (desde el inicio)

1. **Cambio de esquema** (`scripts/schema-change.sh`): `AFI_MAE → PERSON_MASTER`, `NRO_DOC → DOCUMENT_NUMBER`, `EST_AFI → STATUS_CODE`. El portal y los contratos **no cambian**.
2. **Falla del legacy**: `docker compose stop legacy-db` por unos minutos. Las consultas fallan controlado y los retiros **no se pierden ni se duplican**.
3. **Nuevo consumidor**: app móvil consulta afiliados/beneficiarios con la API existente, sin acceso a la base y sin permisos de escritura.

## Contrato obligatorio (gateway `http://localhost:8082`, `Authorization: Bearer <token>`)

Tokens por consumidor en `.env`: `PORTAL_TOKEN`, `SUBSIDIOS_TOKEN`, `MOBILE_TOKEN`.

| Método y ruta | Respuesta esperada |
|---|---|
| `GET /health` | `200` · `{ "status": "UP", "legacy": "UP"\|"DOWN" }` |
| `GET /api/v1/members/{document}` | `200` · `{ document, fullName, status, company: { id, name } }` · `status` ∈ `ACTIVE`, `RETIRED`, `SUSPENDED` |
| `GET /api/v1/members/{document}/beneficiaries` | `200` · lista de `{ document, fullName, relationship }` |
| `GET /api/v1/companies/{id}` | `200` · `{ id, name, activeMembers }` |
| `POST /api/v1/members/{document}/retirements` | Cuerpo `{ requestId, date, reason }` → `201`. Mismo `requestId` → `200` sin duplicar |
| `GET /api/v1/migration/status` | `{ "domains": { "affiliations": "LEGACY\|DUAL\|MODERN", ... } }` |

### Reglas del contrato

- Sin token → `401`. `MOBILE_TOKEN` en un `POST` → `403`.
- Documento inexistente → `404`. Errores con formato `{ "message", "error_id" }`, sin trazas ni SQL.
- Legacy caído: respuesta en **menos de 3 segundos** con `503` y `{ "code": "LEGACY_UNAVAILABLE" }`.
- Un retiro aceptado durante la caída (`202`) se aplica al recuperarse, **una sola vez**.
- Auditoría en `logs/audit.log`: **una línea JSON por petición** con `timestamp`, `consumer` (`portal`/`subsidios`/`mobile`), `endpoint`, `status`, `latency_ms`. El documento va **enmascarado (máximo 4 dígitos visibles)**.
- `sp_registrar_retiro` debe seguir funcionando.
- `POST http://localhost:8091/retiros` (Subsidios) sigue respondiendo como hoy, pero el retiro pasa por el gateway: aparece en `logs/audit.log` con `consumer = subsidios`.
- El servicio de la base se llama `legacy-db`. Los servicios nuevos que hablan con la base se llaman `gateway…` o `adapter…`; **ningún otro servicio nuevo puede conectarse a `legacy-db`**.
- `./rollback.sh affiliations` (raíz, ejecutable): devuelve Afiliaciones a `LEGACY` en **<3 minutos**, código 0; después `/migration/status` muestra `LEGACY` y un retiro desde Subsidios sigue quedando en la base.
- Servicio `tests` en `docker-compose.yml` con `profiles: ["test"]`: corre con `docker compose --profile test run --rm tests`, termina con error si algo falla y deja un reporte **JUnit XML en `./test-results/`**.

## Evento de esquema — detalle

`scripts/schema-change.sh` renombra tabla/columnas **y además recrea** `sp_registrar_retiro` para que funcione sobre `person_master` (el nombre del procedimiento no cambia). Esto significa: las **lecturas** del adapter deben adaptarse a ambos esquemas; la **escritura** por nombre de procedimiento funciona en ambos.

## Entregables (estructura exacta)

```text
src/                   el adapter en carpeta/archivo cuyo nombre contenga "adapter"
tests/
docker-compose.yml     legacy + gateway + consumidores + servicio tests
rollback.sh            ejecutable, en la raíz
openapi.yaml           contrato OpenAPI 3 con las 6 rutas
README.md              documentación del software (11 secciones, regla 12)
AI_USAGE.md            al menos 3 usos con 5 campos
docs/
├── dependency-map.md
├── architecture.md
└── migration-plan.md
```

Regla de oro del adapter: los nombres legacy (`AFI_MAE`, `NRO_DOC`, `EST_AFI`, `LOGMOV`, `sp_registrar_retiro`…) **solo pueden aparecer en archivos de `src/` dentro de una carpeta o archivo cuyo nombre contenga "adapter"** (incluso en comentarios).
