"""Pydantic schemas for health and liveness checks."""

from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Payload returned by health/liveness probes."""

    status: str


class RootResponse(BaseModel):
    """Payload returned by the root liveness endpoint."""

    service: str
    version: str
