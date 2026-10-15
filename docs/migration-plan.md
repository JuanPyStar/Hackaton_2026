# Plan de migración por dominio

Estrategia **Strangler Fig**: cada dominio pasa por `LEGACY → DUAL → MODERN`. En **DUAL** el gateway atiende a los
consumidores nuevos mientras las aplicaciones legacy (Educación, reportes) siguen leyendo la base; el estado vive en
`config/migration-state.json` y se consulta en `GET /api/v1/migration/status`. Avanzar se hace con
`./scripts/set-migration-state.sh <dominio> <ESTADO>`; retroceder, con `./rollback.sh <dominio>`.

| Dominio | Estado | Criterio para avanzar | Rollback |
|---|---|---|---|
| Afiliaciones | DUAL | 7 días seguidos con 0 diferencias en `/api/v1/migration/drift` (muestra de 50 afiliados por corrida) y 0 retiros pendientes en la outbox por más de 5 minutos | `./rollback.sh affiliations`: Afiliaciones vuelve a LEGACY y Subsidios registra otra vez con `sp_registrar_retiro` directo, en menos de 1 minuto |
| Aportes | LEGACY | Contrato `/api/v1/members/{document}/contributions` publicado y 14 días con 0 diferencias entre la API y `APORTES` en una muestra diaria de 100 afiliados | `./rollback.sh contributions`: el portal deja de llamar la ruta nueva y vuelve a la consulta legacy de aportes |
| Reportes | LEGACY | 30 corridas nocturnas seguidas en las que los conteos por empresa y estado calculados por la API coinciden al 100 % con los del job legacy | `./rollback.sh reports` y reactivar el job nocturno que lee `AFI_MAE` y `LOGMOV` directamente |

Siguiente dominio: Aportes

## Afiliaciones en detalle

- **Qué ya está en DUAL:** consultas de afiliado, beneficiarios y empresa por API (portal y app móvil) y la escritura de
  retiros: Subsidios los registra por el gateway con `SUBSIDIOS_TOKEN` y un `requestId` estable.
- **Qué sigue en legacy:** Educación lee `AFI_MAE` directamente (no se puede modificar) y los reportes nocturnos.
- **Evidencia para pasar a MODERN:** el comparador de deriva compara cada afiliado de la muestra entre el gateway y lo que
  ve Educación. Cuando el criterio se cumpla: `./scripts/set-migration-state.sh affiliations MODERN`.
- **Señales para hacer rollback:** diferencias > 0 en la deriva, retiros atascados en la outbox o errores 5xx sostenidos
  del gateway. `./rollback.sh affiliations` es idempotente, no reinicia contenedores y deja la evidencia en consola.
