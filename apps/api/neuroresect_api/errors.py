"""Stable public error envelope without payloads or internal tracebacks."""

from typing import Any


class APIError(Exception):
    def __init__(
        self, status: int, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def envelope(self) -> dict[str, Any]:
        return {
            "error": {"code": self.code, "message": self.message, "details": self.details}
        }
