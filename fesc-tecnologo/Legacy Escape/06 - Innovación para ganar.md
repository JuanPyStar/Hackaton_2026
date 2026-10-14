# 06 · Innovación para ganar

> [!goal] Objetivo: **Product Builder** (mayor nota final) + ser candidato a **FESC Productization** (sin penalizaciones, validador ≥80 %, entregables ≥80 %) + **AI Engineering Award**.

La nota es 70 % automática, así que la innovación va en dos frentes: **los puntos duros que otros no lograrán** y **los diferenciadores que el comité ve**.

## Ideas diferenciadoras (en orden de valor)

### 1. Comparador de deriva ("shadow check") — la joya ⭐
Módulo que en modo DUAL compara periódicamente las respuestas del gateway canónico contra lecturas directas al legacy (por el adapter) y expone:

```json
GET /api/v1/migration/drift → { "differences": 0, "checked": 50, "last_run": "..." }
```

**Convierte el criterio "7 días sin diferencias entre gateway y legacy" en evidencia medible.** Es exactamente lo que hace una migración estranguladora real. Nadie más lo tendrá.

### 2. Outbox durable + replay exactamente-una-vez ⭐
G07+G08+G10+G11 = **200 puntos** del validador y la historia del pitch: *"se cayó la base y no se perdió ni duplicó ni un retiro"*. Es lo que separa un prototipo de algo production-ready (los incidentes históricos del kit lo piden a gritos: retiros perdidos en 2023, duplicados en 2021).

### 3. App móvil real (evento 3)
PWA mobile-first en contenedor `mobile-app` (:8093) que consume la API con `MOBILE_TOKEN` (solo lectura). Demuestra la tesis completa: **un consumidor nuevo sin tocar la base**. Pantalla con búsqueda de afiliado + beneficiarios + estado (bonita para el video).

### 4. Observabilidad con `error_id`
Cada error responde un `error_id` que aparece correlacionado en `logs/audit.log`: trazabilidad petición → error → auditoría. Detalle de ingeniero senior que se ve en la demo.

### 5. Runbook de rollback impecable
`rollback.sh` idempotente que imprime estado antes/después y verifica con `curl` que `/migration/status` quedó en LEGACY. Cumple <3 min con holgura. En el pitch: "y si algo sale mal, un comando revierte el dominio".

### 6. `AI_USAGE.md` como activo (AI Engineering Award)
5–6 usos reales y honestos con la corrección explícita (≥8 palabras), por ejemplo:
> "IA sugirió `localhost` como host de la DB; corregimos a `legacy-db`, el nombre del servicio en la red Docker interna."

### 7. README de producción
Arquitectura con diagrama, flujo de migración, 11 secciones completas: es lo primero que el jurado lee.

## Estrategia del pitch (60 segundos)

| Seg | Qué mostrar |
|---|---|
| 0–10 | El problema: app rota si cambian una columna; retiros perdidos en el histórico |
| 10–30 | La solución: gateway + adapter + modelo canónico, animación del flujo |
| 30–45 | **Demo en vivo**: caer la base (`docker compose stop legacy-db`) → retiro aceptado con 202 → levantar → aplicado 1 sola vez |
| 45–55 | Deriva = 0 y `rollback.sh` en un comando |
| 55–60 | Resultado: X/15 pruebas, migración reversible, siguiente dominio: Retiros |

## Checklist anti-error (lo que hace perder a buenos equipos)

- [ ] Nombres legacy **solo** en `src/**/adapter*` (revisar comentarios)
- [ ] Ningún servicio nuevo conectado a `legacy-db` en el compose (excepto gateway/adapter/tests)
- [ ] `logs/audit.log` sin documentos completos; los 5 campos en cada línea
- [ ] `.env` jamás en Git; sin claves reales en ningún archivo
- [ ] `rollback.sh` con shebang + bit de ejecución (`git update-index --chmod=+x rollback.sh`)
- [ ] `tests` con `profiles: ["test"]` y JUnit en `test-results/`
- [ ] `mobile-app` **sin** `depends_on: legacy-db`
- [ ] README: comandos exactos `docker compose … up`, `./rollback.sh`, las 6 rutas y `--profile test run --rm tests`
