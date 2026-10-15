# Mapa de dependencias del legacy

Quién lee y quién escribe cada tabla de la base legacy **hoy** (antes de la migración). Fuente: `docs/procesos.md`,
el código de `services/educacion` y `services/subsidios`, y el procedimiento `sp_registrar_retiro` (`db/init/03_procedures.sql`).

| Aplicación | Tabla | Operación | Criticidad |
|---|---|---|---|
| Educación | AFI_MAE | Lectura | Alta |
| Educación | EMPRESA | Lectura | Media |
| Subsidios | AFI_MAE | Escritura | Alta |
| Subsidios | LOGMOV | Escritura | Alta |
| Reportes nocturnos | AFI_MAE | Lectura | Media |
| Reportes nocturnos | LOGMOV | Lectura | Media |

## Cómo se leyó cada fila

- **Educación** (`educacion-app`) consulta `AFI_MAE` con `LEFT JOIN EMPRESA` para validar la afiliación antes de matricular.
  Alta en `AFI_MAE` porque sin ella no matricula; Media en `EMPRESA` porque solo muestra el nombre de la empresa.
  No se puede modificar: por eso el cambio de esquema se hace con la ventana DUAL y el comparador de deriva.
- **Subsidios** (`subsidios-app`) llama `sp_registrar_retiro`, que actualiza `AFI_MAE` (`EST_AFI = 'R'`, `FEC_RET`) e
  inserta el movimiento `RET` en `LOGMOV`. Es la única escritura del dominio y la que causó los incidentes de 2021
  (duplicado) y 2023 (retiros perdidos): criticidad Alta.
- **Reportes nocturnos** cuentan afiliados por empresa y estado (`AFI_MAE`) y movimientos (`LOGMOV`). Corren de noche
  y toleran un retraso: criticidad Media.
- **Portal de servicios** no aparece porque nunca tocó la base: solo habla HTTP con `GATEWAY_URL`.
- `AFI_BEN` y `APORTES` no tienen consumidores directos hoy; `AFI_BEN` solo la lee el gateway.

## Después de la migración (DUAL)

El gateway (`src/`) es ahora quien lee `AFI_MAE`, `AFI_BEN` y `EMPRESA` y ejecuta `sp_registrar_retiro` en nombre del
portal, Subsidios y la app móvil. Para la idempotencia usa una tabla propia, `gw_retirement_request`, que no comparte con
ninguna aplicación legacy. Esas dependencias del gateway no van en la tabla porque son la capa nueva, no el legacy.
