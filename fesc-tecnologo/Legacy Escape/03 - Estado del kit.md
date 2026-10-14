# 03 · Estado del kit — qué hay vs qué falta

## Qué YA está en la carpeta (no se rompe, se complementa)

```text
fesc-tecnologo/
├── docker-compose.yml        legacy-db, educacion-app(:8090), portal-client(:8092), subsidios-app(:8091)
├── db/init/
│   ├── 01_schema.sql         empresa, afi_mae, afi_ben, aportes, logmov (+índices)
│   ├── 02_data.sql           15 empresas, ~250 afiliados, beneficiarios (semilla 2026)
│   └── 03_procedures.sql     sp_registrar_retiro (NO idempotente)
├── services/
│   ├── educacion/            NO modificable. Lee directo; ya tolera ambos esquemas
│   ├── portal/               NO modificable. Solo habla con GATEWAY_URL + PORTAL_TOKEN
│   └── subsidios/            SÍ modificable. Hoy llama sp_registrar_retiro directo
├── scripts/schema-change.sh  evento 1: renombra + recrea el SP sobre person_master
├── docs/                     plantillas: dependency-map, architecture, migration-plan
│   ├── procesos.md           pistas de las 6 dependencias reales
│   ├── modelo-legacy.md      tablas, columnas, códigos (A/R/S, C/H/P/M)
│   └── incidentes-historicos.md  duplicados 2021, retiros perdidos 2023, docs en logs 2025
├── validator                 ./validator check (G01–G06, G12–G14) y entregables
├── reset.sh                  vuelve todo al estado inicial (borra volúmenes)
├── .env.example              POSTGRES_*, LEGACY_DB_*, GATEWAY_URL, PORTAL/SUBSIDIOS/MOBILE_TOKEN
├── .validator.json           docs de prueba: 1019282447, 6039066119; inexistente 0000000001
├── README.md / AI_USAGE.md   plantillas vacías (llenar)
└── RETO.md, RUBRICA.md, KIT.md, COMO-ENTREGAR.md
```

### Datos clave del legacy

- `afi_mae.est_afi`: `A`=activo, `R`=retirado, `S`=suspendido → API: `ACTIVE` / `RETIRED` / `SUSPENDED`
- `afi_ben.cod_par`: `C`=cónyuge, `H`=hijo(a), `P`=padre, `M`=madre
- `sp_registrar_retiro(doc, fecha, motivo, usuario)`: pone `R` + `FEC_RET` e inserta `RET` en `LOGMOV`. **No es idempotente** (cada llamada inserta).
- Tablas que NO renombra el cambio de esquema: `afi_ben`, `empresa`, `aportes`, `logmov`.

## Estado actual del workspace

- [ ] **No es repositorio Git todavía** (`git init` pendiente) ← hacer primero
- [ ] No hay `.env` (copiar de `.env.example` con tokens propios)
- [ ] No existe el gateway ni `src/`
- [ ] No existe `rollback.sh`
- [ ] No existe `openapi.yaml`
- [ ] No hay servicio `tests` ni `test-results/`
- [ ] Plantillas de docs y README vacíos

## Qué falta construir (todo lo que puntúa)

| # | Componente | Puntos en juego |
|---|---|---|
| 1 | Gateway (:8082): auth, 6 rutas, canónico, errores | G01–G06 = 150 |
| 2 | Adapter con detección dual de esquema + idempotencia | G07, G08, G09, G13, GE01 |
| 3 | Resiliencia: circuit breaker + outbox durable + replay | G10, G11 = 100 |
| 4 | Auditoría con masking + `error_id` | G12 = 30 |
| 5 | Migración de subsidios + estado compartido + rollback.sh | G14, G15, GE04 = 43 |
| 6 | Servicio `tests` con JUnit XML (≥10 pruebas) | GE05 = 3 |
| 7 | openapi.yaml + 3 docs + README + AI_USAGE | GE02, GE03, GE06, GE07, GE09, GE11 = 14 |
| 8 | App móvil + diferenciadores de innovación | pitch, Product Builder |

## Comandos de verificación desde el kit

```bash
cp .env.example .env
mkdir -p logs
docker compose up -d --build
curl http://localhost:8090/afiliados/1019282447   # lo que ve Educación
./validator check
./validator entregables
./reset.sh                                         # después de pruebas destructivas
```
