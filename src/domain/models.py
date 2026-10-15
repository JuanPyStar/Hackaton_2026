"""Modelo canónico del dominio Afiliaciones.

Es el único vocabulario que conocen la API y los consumidores. El adapter traduce
desde y hacia el esquema heredado; nada fuera del adapter conoce tablas ni códigos.
"""

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class MemberStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    SUSPENDED = "SUSPENDED"


class Relationship(str, Enum):
    SPOUSE = "SPOUSE"
    CHILD = "CHILD"
    FATHER = "FATHER"
    MOTHER = "MOTHER"
    OTHER = "OTHER"


@dataclass(frozen=True)
class CompanyRef:
    id: str
    name: str


@dataclass(frozen=True)
class Member:
    document: str
    fullName: str
    status: MemberStatus
    company: Optional[CompanyRef]

    def to_dict(self) -> dict:
        return {
            "document": self.document,
            "fullName": self.fullName,
            "status": self.status.value,
            "company": asdict(self.company) if self.company else None,
        }


@dataclass(frozen=True)
class Beneficiary:
    document: str
    fullName: str
    relationship: Relationship

    def to_dict(self) -> dict:
        return {"document": self.document, "fullName": self.fullName, "relationship": self.relationship.value}


@dataclass(frozen=True)
class Company:
    id: str
    name: str
    activeMembers: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RetirementCommand:
    request_id: str
    document: str
    date: date
    reason: str
    consumer: str


@dataclass
class RetirementResult:
    requestId: str
    document: str
    date: str
    reason: str
    status: str = MemberStatus.RETIRED.value
    movementId: Optional[int] = None
    replayed: bool = field(default=False, compare=False)

    def to_dict(self) -> dict:
        return {
            "requestId": self.requestId,
            "document": self.document,
            "date": self.date,
            "reason": self.reason,
            "status": self.status,
            "movementId": self.movementId,
        }


def full_name(*parts: Optional[str]) -> str:
    """Une nombres y apellidos sin nulos y con un solo espacio."""
    return " ".join(" ".join(p.split()) for p in parts if p and p.strip())
