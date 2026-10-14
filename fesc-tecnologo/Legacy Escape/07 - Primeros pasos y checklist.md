# 07 · Primeros pasos y checklist de entrega

## Fase 0 — hoy, en este orden

- [ ] **1. Git init + commit inicial**
  ```bash
  git init
  git add -A
  git commit -m "Importa el kit FESC Legacy Escape"
  ```
- [ ] **2. `.env` local** (nunca se versiona; `.gitignore` ya lo excluye)
  ```bash
  cp .env.example .env
  # editar: generar tokens propios fuertes para PORTAL/SUBSIDIOS/MOBILE_TOKEN
  ```
- [ ] **3. Levantar el kit y ver la línea base**
  ```bash
  mkdir -p logs
  docker compose up -d --build
  docker compose ps
  curl http://localhost:8090/afiliados/1019282447    # lo que ve Educación
  ./validator check
  ```
- [ ] **4. Repositorio público** (GitHub/GitLab/Bitbucket, sin README ni licencia)
  ```bash
  git remote add origin https://github.com/<usuario>/<proyecto>.git
  git branch -M main
  git push -u origin main
  ```
- [ ] **5. Registrar el enlace en la plataforma** (https://hackafesc.ingsoftwarefesc.com → **Mi equipo**). Verificar que diga "público".
- [ ] **6. Repartir el trabajo** (pareja): cada integrante debe generar **≥3 commits** con su nombre y correo.

## Rutina durante el hackaton

- [ ] Commit por cada avance real, mensaje descriptivo ("agrega idempotencia por requestId en el retiro", no "update"). Mínimo **10 commits** al final.
- [ ] `./validator check` después de cada cambio.
- [ ] `./validator entregables` antes de cada push importante.
- [ ] `git push` seguido (la plataforma califica el último commit previo al cierre).
- [ ] Registrar usos de IA en [[02 - Reglas y calificación]] → volcarlos en `AI_USAGE.md`.

## Checklist final (antes de la hora límite)

### Código y entorno
- [ ] `docker compose up -d --build` funciona desde cero (sin volúmenes previos)
- [ ] `./validator check` → G01–G06, G12–G14 PASS
- [ ] Ensayos manuales de G07–G11 y G15 verificados (ver [[05 - Plan de desarrollo]])
- [ ] `docker compose --profile test run --rm tests` → código 0 + JUnit con ≥10 pruebas en `test-results/`
- [ ] `./rollback.sh affiliations` → código 0, `<3 min`, estado LEGACY, subsidios sigue escribiendo
- [ ] `scripts/schema-change.sh` no rompe nada

### Entregables (rutas exactas)
- [ ] `src/` con el adapter (nombres legacy solo ahí)
- [ ] `tests/`
- [ ] `openapi.yaml` con las 6 rutas
- [ ] `rollback.sh` ejecutable
- [ ] `docs/dependency-map.md` — 6 filas exactas, sin filas de más
- [ ] `docs/migration-plan.md` — ≥3 dominios + `Siguiente dominio:`
- [ ] `docs/architecture.md` — 5 secciones ≥20 palabras, ≥2 alternativas
- [ ] `README.md` — 11 secciones completas (comandos, 6 rutas, servicios del compose, variables de `.env.example`)
- [ ] `AI_USAGE.md` — ≥3 usos con 5 campos, corrección ≥8 palabras

### Reglas rojas
- [ ] `.env` NUNCA en el historial de Git
- [ ] Ningún valor real de token/clave escrito en ningún archivo
- [ ] `docker-compose.yml` sin `privileged`, `cap_add`, `devices`, `network_mode: host`, `pid: host` ni montajes fuera del repo
- [ ] Ningún servicio nuevo (fuera de gateway/adapter/tests) conectado a `legacy-db`
- [ ] Todos los textos en `.md` (nada de `.docx`/`.pdf`) y <1 MB

### Plataforma
- [ ] Repo público registrado en **Mi equipo** (verificado)
- [ ] Video pitch **≤60 s** en Drive, "Cualquier persona con el enlace", registrado
- [ ] **No modificar el video ni subir nada después de la hora límite**
