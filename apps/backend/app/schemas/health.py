"""Health check 回應 Schema。"""
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    platform: str
    python_version: str
