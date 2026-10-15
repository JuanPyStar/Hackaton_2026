"""Adapter (Anti-Corruption Layer) hacia la base legacy.

ÚNICO lugar del gateway que conoce tablas, columnas, códigos y procedimientos legacy.
Hacia afuera solo entrega objetos del modelo canónico (domain.models).

Detección doble de esquema:
  - original:   AFI_MAE(NRO_DOC, EST_AFI)
  - renombrado: PERSON_MASTER(DOCUMENT_NUMBER, STATUS_CODE)  (scripts/schema-change.sh)
El esquema activo se detecta con to_regclass y se cachea; si una consulta falla por
tabla/columna inexistente (cambio de esquema en caliente) se re-detecta y se reintenta.

Idempotencia de retiros: en UNA transacción se reserva el requestId en la tabla propia
del gateway (gw_retirement_request), se llama sp_registrar_retiro y se guarda el
movimiento. Si algo falla, el rollback libera el requestId: exactamente una vez.
"""

import os
import threading
from dataclasses import dataclass
from datetime import date

import psycopg2
import psycopg2.errors

from domain.errors import Conflict, DomainError, LegacyUnavailable, NotFound
from domain.models import (Beneficiary, Company, CompanyRef, Member, MemberStatus,
                           Relationship, RetirementCommand, RetirementResult, full_name)

CONNECT_TIMEOUT_S = int(os.environ.get("LEGACY_CONNECT_TIMEOUT", "2"))
STATEMENT_TIMEOUT_MS = int(os.environ.get("LEGACY_STATEMENT_TIMEOUT_MS", "2500"))

# Códigos legacy -> modelo canónico
_STATUS = {"A": MemberStatus.ACTIVE, "R": MemberStatus.RETIRED, "S": MemberStatus.SUSPENDED}
_RELATIONSHIP = {"C": Relationship.SPOUSE, "H": Relationship.CHILD, "P": Relationship.FATHER, "M": Relationship.MOTHER}


@dataclass(frozen=True)
class _Schema:
    name: str
    members: str
    document: str
    status: str


ORIGINAL = _Schema("original", "afi_mae", "nro_doc", "est_afi")
RENAMED = _Schema("renamed", "person_master", "document_number", "status_code")

_SCHEMA_ERRORS = (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn)
_UNAVAILABLE_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError,
                       psycopg2.errors.QueryCanceled, psycopg2.errors.AdminShutdown)

_IDEMPOTENCY_DDL = """
CREATE TABLE IF NOT EXISTS gw_retirement_request (
    request_id  VARCHAR(100) PRIMARY KEY,
    document    VARCHAR(15)  NOT NULL,
    retire_date DATE         NOT NULL,
    reason      VARCHAR(200) NOT NULL,
    consumer    VARCHAR(20)  NOT NULL,
    movement_id INTEGER,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
)
"""


class LegacyRepository:
    def __init__(self):
        self._schema = None
        self._lock = threading.Lock()
        self._idempotency_ready = False

    # ------------------------------------------------------------------ conexión
    def _connect(self):
        try:
            conn = psycopg2.connect(
                host=os.environ.get("LEGACY_DB_HOST", "legacy-db"),
                port=int(os.environ.get("LEGACY_DB_PORT", "5432")),
                dbname=os.environ.get("POSTGRES_DB", "legacy"),
                user=os.environ.get("POSTGRES_USER", "legacy"),
                password=os.environ.get("POSTGRES_PASSWORD", ""),
                connect_timeout=CONNECT_TIMEOUT_S,
                options="-c statement_timeout={0}".format(STATEMENT_TIMEOUT_MS),
                application_name="gateway-adapter",
            )
        except _UNAVAILABLE_ERRORS as exc:
            raise LegacyUnavailable() from exc
        return conn

    def _detect_schema(self, cur) -> _Schema:
        cur.execute("SELECT to_regclass('public.person_master') IS NOT NULL")
        return RENAMED if cur.fetchone()[0] else ORIGINAL

    def _schema_for(self, cur) -> _Schema:
        if self._schema is None:
            with self._lock:
                if self._schema is None:
                    self._schema = self._detect_schema(cur)
        return self._schema

    def _run(self, work, *, autocommit=True):
        """Ejecuta work(cur, schema) traduciendo fallas y reintentando ante cambio de esquema."""
        for attempt in (1, 2):
            conn = self._connect()
            conn.autocommit = autocommit
            try:
                with conn.cursor() as cur:
                    schema = self._schema_for(cur)
                    result = work(conn, cur, schema)
                if not autocommit:
                    conn.commit()
                return result
            except _SCHEMA_ERRORS:
                self._rollback(conn)
                self._schema = None          # el DBA cambió el esquema: re-detectar
                if attempt == 2:
                    raise DomainError()
            except _UNAVAILABLE_ERRORS as exc:
                self._rollback(conn)
                raise LegacyUnavailable() from exc
            except DomainError:
                self._rollback(conn)
                raise
            except psycopg2.Error as exc:
                self._rollback(conn)
                raise DomainError() from exc
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def _rollback(conn):
        try:
            if not conn.closed and not conn.autocommit:
                conn.rollback()
        except Exception:
            pass

    # ------------------------------------------------------------------ salud
    def ping(self) -> bool:
        try:
            conn = self._connect()
        except LegacyUnavailable:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone()[0] == 1
        except psycopg2.Error:
            return False
        finally:
            conn.close()

    def active_schema(self) -> str:
        return self._schema.name if self._schema else "unknown"

    # ------------------------------------------------------------------ lecturas
    def get_member(self, document: str) -> Member:
        def work(conn, cur, s):
            cur.execute(
                "SELECT a.{doc}, a.nom1, a.nom2, a.ape1, a.ape2, a.{st}, e.cod_emp, e.nom_emp "
                "FROM {tbl} a LEFT JOIN empresa e ON e.cod_emp = a.cod_emp "
                "WHERE a.{doc} = %s".format(doc=s.document, st=s.status, tbl=s.members),
                (document,),
            )
            return cur.fetchone()

        row = self._run(work)
        if row is None:
            raise NotFound("No existe un afiliado con ese documento")
        company = CompanyRef(id=str(row[6]).strip(), name=row[7]) if row[6] else None
        return Member(
            document=str(row[0]).strip(),
            fullName=full_name(row[1], row[2], row[3], row[4]),
            status=_STATUS.get((row[5] or "").strip().upper(), MemberStatus.SUSPENDED),
            company=company,
        )

    def get_beneficiaries(self, document: str) -> list:
        def work(conn, cur, s):
            cur.execute("SELECT 1 FROM {tbl} WHERE {doc} = %s".format(tbl=s.members, doc=s.document), (document,))
            if cur.fetchone() is None:
                return None
            cur.execute(
                "SELECT nro_doc_ben, nom1, nom2, ape1, ape2, cod_par FROM afi_ben "
                "WHERE nro_doc = %s ORDER BY nro_doc_ben",
                (document,),
            )
            return cur.fetchall()

        rows = self._run(work)
        if rows is None:
            raise NotFound("No existe un afiliado con ese documento")
        return [
            Beneficiary(
                document=str(r[0]).strip(),
                fullName=full_name(r[1], r[2], r[3], r[4]),
                relationship=_RELATIONSHIP.get((r[5] or "").strip().upper(), Relationship.OTHER),
            )
            for r in rows
        ]

    def get_company(self, company_id: str) -> Company:
        def work(conn, cur, s):
            cur.execute(
                "SELECT e.cod_emp, e.nom_emp, "
                "(SELECT count(*) FROM {tbl} a WHERE a.cod_emp = e.cod_emp AND a.{st} = 'A') "
                "FROM empresa e WHERE e.cod_emp = %s".format(tbl=s.members, st=s.status),
                (company_id,),
            )
            return cur.fetchone()

        row = self._run(work)
        if row is None:
            raise NotFound("No existe una empresa con ese identificador")
        return Company(id=str(row[0]).strip(), name=row[1], activeMembers=int(row[2]))

    def sample_documents(self, size: int) -> list:
        """Documentos al azar para el comparador de deriva (shadow check)."""
        def work(conn, cur, s):
            cur.execute("SELECT {doc} FROM {tbl} ORDER BY random() LIMIT %s".format(doc=s.document, tbl=s.members),
                        (size,))
            return [str(r[0]).strip() for r in cur.fetchall()]

        return self._run(work)

    def warm_up(self):
        """Detecta el esquema y prepara la tabla de idempotencia al arrancar (si la base responde)."""
        self._ensure_idempotency_table()

    # ------------------------------------------------------------------ escritura
    def _ensure_idempotency_table(self):
        if self._idempotency_ready:
            return

        def work(conn, cur, s):
            try:
                cur.execute(_IDEMPOTENCY_DDL)
            except psycopg2.errors.UniqueViolation:
                pass   # otro hilo la creó al mismo tiempo

        self._run(work)
        self._idempotency_ready = True

    def register_retirement(self, cmd: RetirementCommand) -> RetirementResult:
        """Registra el retiro una sola vez por requestId (transacción única)."""
        self._ensure_idempotency_table()
        reason = (cmd.reason or "RETIRO")[:200]

        def work(conn, cur, s):
            cur.execute(
                "INSERT INTO gw_retirement_request (request_id, document, retire_date, reason, consumer) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (request_id) DO NOTHING RETURNING request_id",
                (cmd.request_id, cmd.document, cmd.date, reason, cmd.consumer),
            )
            if cur.fetchone() is None:
                cur.execute(
                    "SELECT document, retire_date, reason, movement_id FROM gw_retirement_request "
                    "WHERE request_id = %s",
                    (cmd.request_id,),
                )
                prev = cur.fetchone()
                if prev[0] != cmd.document:
                    raise Conflict("El requestId ya se usó para otro afiliado")
                return RetirementResult(requestId=cmd.request_id, document=prev[0], date=prev[1].isoformat(),
                                        reason=prev[2], movementId=prev[3], replayed=True)
            try:
                cur.execute("SELECT sp_registrar_retiro(%s, %s, %s, %s)",
                            (cmd.document, cmd.date, reason, cmd.consumer.upper()[:20]))
            except psycopg2.errors.RaiseException as exc:
                if "AFI-404" in str(exc):
                    raise NotFound("No existe un afiliado con ese documento") from exc
                raise
            movement_id = cur.fetchone()[0]
            cur.execute("UPDATE gw_retirement_request SET movement_id = %s WHERE request_id = %s",
                        (movement_id, cmd.request_id))
            return RetirementResult(requestId=cmd.request_id, document=cmd.document, date=cmd.date.isoformat(),
                                    reason=reason, movementId=movement_id)

        return self._run(work, autocommit=False)


repository = LegacyRepository()
