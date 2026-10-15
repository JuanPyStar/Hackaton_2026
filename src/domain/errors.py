"""Errores de dominio. La capa API los traduce a HTTP con {message, error_id}."""


class DomainError(Exception):
    status_code = 500
    public_message = "Error interno del gateway"

    def __init__(self, message: str = None):
        super().__init__(message or self.public_message)
        self.message = message or self.public_message


class NotFound(DomainError):
    status_code = 404
    public_message = "Recurso no encontrado"


class InvalidRequest(DomainError):
    status_code = 400
    public_message = "Solicitud inválida"


class Conflict(DomainError):
    status_code = 409
    public_message = "Conflicto con una solicitud previa"


class LegacyUnavailable(DomainError):
    status_code = 503
    public_message = "El sistema legacy no está disponible en este momento"
