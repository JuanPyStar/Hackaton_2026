# 05 · Plan de desarrollo — 10 fases

> [!tip] Regla de oro
> Después de **cada fase**: `./validator check` + `./validator entregables` en verde antes de pasar a la siguiente. Commits pequeños y descriptivos en todo el rato (≥10, ≥3 por integrante).

## Fases ordenadas por puntos

| Fase | Qué se hace | Esfuerzo | Puntos en juego |
|---|---|---:|---|
| **0. Puesta a punto** | `git init` + commit "Importa el kit", `cp .env.example .env` con tokens propios, `docker compose up -d --build`, `./validator check` baseline, crear repo **público**, push y **registrar en la plataforma** | 0.5 h | Evita NO CALIFICADO |
| **1. Gateway base** | Skeleton FastAPI :8082; middleware Bearer (401/403); modelo canónico; adapter con detección dual; `GET /health`, `/members/{doc}`, `/beneficiaries`, `/companies/{id}`; 404 con `{message, error_id}` | 3 h | **G01–G06 = 150** |
| **2. Escritura migrada** | `POST /retirements` con idempotencia transaccional vía `sp_registrar_retiro`; verificar que Educación lo ve | 2 h | **G07+G08+G13 = 120** |
| **3. Resiliencia** | Circuit breaker + 503 <3 s + outbox durable + worker replay exactamente-una-vez | 2.5 h | **G10+G11 = 100** |
| **4. Cambio de esquema** | Correr `scripts/schema-change.sh` a mano → `./validator check` igual que antes → `./reset.sh` | 1 h | **G09 = 60** |
| **5. Dominio migrado** | `subsidios-app` por el gateway (conservando camino legacy), `config/migration-state.json`, `/migration/status`, `rollback.sh affiliations` | 2 h | **G14+G15+GE04 = 43** |
| **6. Auditoría** | Middleware `logs/audit.log` con masking y `error_id` correlacionado | 1 h | **G12 = 30** |
| **7. Pruebas** | Servicio `tests` (perfil `test`), ≥10 pruebas pytest contra la API, JUnit XML en `test-results/` | 2 h | **GE05 = 3** + red de seguridad |
| **8. Documentos** | `dependency-map.md` (6 filas exactas), `migration-plan.md` (≥3 dominios), `architecture.md` (5 secciones ≥20 palabras), `openapi.yaml` (6 rutas), `README.md` (11 secciones), `AI_USAGE.md` (≥3 usos) | 3 h | **GE01–GE03, GE06, GE07, GE09, GE11 ≈ 18** |
| **9. Innovación** | App móvil PWA + comparador de deriva + extras (ver [[06 - Innovación para ganar]]) | 3–4 h | Diferenciación + pitch |
| **10. Cierre** | Validadores en verde, video ≤60 s, push final, registrar pitch en la plataforma **antes** del cierre | 1 h | **GE10 = 5** + evitar penalizaciones |

## Ensayo manual de las pruebas "solo oficial"

```bash
# G07 + G08 — retiro e idempotencia
curl -X POST http://localhost:8082/api/v1/members/1019282447/retirements \
  -H "Authorization: Bearer $PORTAL_TOKEN" -H "Content-Type: application/json" \
  -d '{"requestId":"prueba-1","date":"2026-10-05","reason":"voluntario"}'   # → 201
# repetir el mismo requestId → 200; contar filas en LOGMOV: debe ser 1
docker compose exec legacy-db psql -U legacy -d legacy \
  -c "SELECT count(*) FROM logmov WHERE nro_doc='1019282447' AND tip_mov='RET'"

# G09 — cambio de esquema
./scripts/schema-change.sh && ./validator check      # mismos resultados que antes
./reset.sh                                            # volver a estado inicial

# G10 + G11 — caída y recuperación
docker compose stop legacy-db
curl -w '%{time_total}\n' http://localhost:8082/health            # 200, legacy DOWN
curl -X POST .../retirements -d '{"requestId":"caida-1",...}'      # 202 (aceptado)
docker compose start legacy-db                                     # worker repite… 1 sola vez

# G15 — subsidios
curl -X POST http://localhost:8091/retiros -H 'Content-Type: application/json' \
  -d '{"documento":"1019282447","fecha":"2026-10-05","motivo":"prueba"}'
grep subsidios logs/audit.log | tail -1        # consumer = subsidios

# GE04 — rollback (debe durar <3 min y terminar en 0)
./rollback.sh affiliations
curl -s http://localhost:8082/api/v1/migration/status -H "Authorization: Bearer $PORTAL_TOKEN"
./reset.sh                                     # después de todo: estado limpio
```

## Criterios de aceptación por fase

- [ ] **F1:** `./validator check` → G01–G06 PASS
- [ ] **F2:** retiro visible para Educación (`curl :8090/afiliados/<doc>` muestra `RETIRADO`); duplicado no crea fila extra
- [ ] **F3:** con la DB detenida: 503 en <3 s; retiros en cola; al levantar, aplicados 1 sola vez
- [ ] **F4:** tras `schema-change.sh`, check idéntico
- [ ] **F5:** `/migration/status` = DUAL; `rollback.sh` → LEGACY y subsidios sigue escribiendo
- [ ] **F6:** últimas 200 líneas de audit con 5 campos y sin documentos completos
- [ ] **F7:** `docker compose --profile test run --rm tests` → 0 y JUnit con ≥10 tests
- [ ] **F8:** `./validator entregables` sin faltantes
- [ ] **F10:** repo público + registrado + pitch ≤60 s + ambos con ≥3 commits
