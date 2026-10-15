"""Pruebas de contrato contra el gateway en funcionamiento (solo HTTP, sin tocar la base).

Se ejecutan con:  docker compose --profile test run --rm tests
Las pruebas de escritura usan un afiliado que YA estaba retirado en los datos del kit, para
no alterar los datos que revisan otras verificaciones (su estado sigue siendo RETIRED).
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid

import pytest

GATEWAY = os.environ.get("GATEWAY_URL", "http://gateway:8082").rstrip("/")
PORTAL = os.environ.get("PORTAL_TOKEN", "")
SUBSIDIOS = os.environ.get("SUBSIDIOS_TOKEN", "")
MOBILE = os.environ.get("MOBILE_TOKEN", "")
AUDIT_LOG = os.environ.get("AUDIT_LOG_PATH", "/app/logs/audit.log")

MEMBER = "6039066119"            # afiliado con empresa 2014
MEMBER_WITH_BENEFICIARY = "1019282447"
RETIRED_MEMBER = "1322694345"    # ya retirado en los datos del kit
MISSING = "0000000001"
LEGACY_WORDS = re.compile(r"(?i)\b(nro_doc|afi_mae|afi_ben|est_afi|cod_emp|nom_emp|cod_par|logmov|person_master|"
                          r"document_number|status_code|select|traceback|psycopg)\b")


def call(method, path, token=None, body=None, timeout=10):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(GATEWAY + path, data=data, headers=headers, method=method)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        status = exc.code
    elapsed = time.time() - started
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = None
    return status, payload, raw, elapsed


def retirement(document, request_id, token=PORTAL, date="2026-10-05"):
    return call("POST", "/api/v1/members/{0}/retirements".format(document), token,
                {"requestId": request_id, "date": date, "reason": "prueba automatizada"})


@pytest.fixture(scope="session", autouse=True)
def gateway_ready():
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            status, body, _, _ = call("GET", "/health", timeout=3)
            if status == 200 and body.get("legacy") == "UP":
                return
        except Exception:
            pass
        time.sleep(1)
    pytest.fail("El gateway no quedó disponible en 60 s")


# ------------------------------------------------------------------ salud
def test_health_responde_up_con_estado_del_legacy():
    status, body, _, elapsed = call("GET", "/health")
    assert status == 200
    assert body["status"] == "UP"
    assert body["legacy"] in ("UP", "DOWN")
    assert elapsed < 3


# ------------------------------------------------------------------ autenticación
def test_sin_token_responde_401_con_formato_de_error():
    status, body, _, _ = call("GET", "/api/v1/members/" + MEMBER)
    assert status == 401
    assert body["message"] and body["error_id"]


def test_token_invalido_responde_401():
    status, _, _, _ = call("GET", "/api/v1/members/" + MEMBER, "token-que-no-existe")
    assert status == 401


def test_mobile_puede_leer():
    status, body, _, _ = call("GET", "/api/v1/members/" + MEMBER, MOBILE)
    assert status == 200
    assert body["document"] == MEMBER


def test_mobile_no_puede_escribir_403():
    status, body, _, _ = retirement(MISSING, "pytest-mobile-" + uuid.uuid4().hex, token=MOBILE)
    assert status == 403
    assert body["error_id"]


# ------------------------------------------------------------------ consultas (modelo canónico)
def test_afiliado_en_modelo_canonico_sin_columnas_legacy():
    status, body, raw, _ = call("GET", "/api/v1/members/" + MEMBER, PORTAL)
    assert status == 200
    assert set(body) == {"document", "fullName", "status", "company"}
    assert body["status"] in ("ACTIVE", "RETIRED", "SUSPENDED")
    assert set(body["company"]) == {"id", "name"}
    assert "  " not in body["fullName"] and body["fullName"] == body["fullName"].strip()
    assert not LEGACY_WORDS.search(raw)


def test_afiliado_inexistente_404_sin_trazas_ni_sql():
    status, body, raw, _ = call("GET", "/api/v1/members/" + MISSING, PORTAL)
    assert status == 404
    assert set(body) >= {"message", "error_id"}
    assert not LEGACY_WORDS.search(raw)


def test_documento_no_numerico_400():
    status, body, _, _ = call("GET", "/api/v1/members/abc", PORTAL)
    assert status == 400
    assert body["error_id"]


def test_beneficiarios_lista_con_parentesco_canonico():
    status, body, _, _ = call("GET", "/api/v1/members/{0}/beneficiaries".format(MEMBER_WITH_BENEFICIARY), PORTAL)
    assert status == 200
    assert isinstance(body, list) and body
    for item in body:
        assert set(item) == {"document", "fullName", "relationship"}
        assert item["relationship"] in ("SPOUSE", "CHILD", "FATHER", "MOTHER", "OTHER")


def test_beneficiarios_de_afiliado_inexistente_404():
    status, _, _, _ = call("GET", "/api/v1/members/{0}/beneficiaries".format(MISSING), PORTAL)
    assert status == 404


def test_empresa_con_afiliados_activos():
    _, member, _, _ = call("GET", "/api/v1/members/" + MEMBER, PORTAL)
    company_id = member["company"]["id"]
    status, body, _, _ = call("GET", "/api/v1/companies/{0}".format(company_id), PORTAL)
    assert status == 200
    assert str(body["id"]) == str(company_id)
    assert body["name"] == member["company"]["name"]
    assert isinstance(body["activeMembers"], int) and body["activeMembers"] >= 0


def test_empresa_inexistente_404():
    status, body, _, _ = call("GET", "/api/v1/companies/99999", PORTAL)
    assert status == 404
    assert body["error_id"]


# ------------------------------------------------------------------ retiros e idempotencia
def test_retiro_201_y_repetido_200_sin_duplicar():
    request_id = "pytest-" + uuid.uuid4().hex
    first = retirement(RETIRED_MEMBER, request_id, token=SUBSIDIOS)
    second = retirement(RETIRED_MEMBER, request_id, token=SUBSIDIOS)
    assert first[0] == 201
    assert second[0] == 200
    assert first[1]["movementId"] == second[1]["movementId"]
    assert first[1]["status"] == "RETIRED"


def test_request_id_reutilizado_para_otro_afiliado_409():
    request_id = "pytest-" + uuid.uuid4().hex
    assert retirement(RETIRED_MEMBER, request_id)[0] == 201
    status, body, _, _ = retirement(MEMBER, request_id)
    assert status == 409
    assert body["error_id"]


def test_retiro_de_afiliado_inexistente_404():
    status, body, _, _ = retirement(MISSING, "pytest-" + uuid.uuid4().hex)
    assert status == 404
    assert body["error_id"]


def test_retiro_con_cuerpo_invalido_400():
    status, body, _, _ = call("POST", "/api/v1/members/{0}/retirements".format(RETIRED_MEMBER), PORTAL,
                              {"date": "no-es-fecha"})
    assert status == 400
    assert body["message"] and body["error_id"]


# ------------------------------------------------------------------ migración
def test_estado_de_migracion_valido():
    status, body, _, _ = call("GET", "/api/v1/migration/status", PORTAL)
    assert status == 200
    assert body["domains"]["affiliations"] in ("LEGACY", "DUAL", "MODERN")


def test_comparador_de_deriva_responde_metricas():
    status, body, _, _ = call("GET", "/api/v1/migration/drift?sample=5", PORTAL)
    assert status == 200
    assert {"checked", "differences", "lastRun"} <= set(body)
    assert body["differences"] == 0


# ------------------------------------------------------------------ auditoría
def test_auditoria_con_campos_y_documentos_enmascarados():
    call("GET", "/api/v1/members/" + MEMBER, PORTAL)
    time.sleep(0.3)
    if not os.path.exists(AUDIT_LOG):
        pytest.skip("logs/audit.log no está montado en el contenedor de pruebas")
    lines = [l for l in open(AUDIT_LOG, encoding="utf-8").read().splitlines() if l.strip()][-200:]
    assert lines
    for line in lines:
        entry = json.loads(line)
        assert {"timestamp", "consumer", "endpoint", "status", "latency_ms"} <= set(entry)
        visible = " ".join(str(entry.get(k, "")) for k in ("endpoint", "request_id"))
        assert not re.search(r"\d{5,}", visible), "documento sin enmascarar"
    assert any(json.loads(l)["consumer"] == "portal" for l in lines)
