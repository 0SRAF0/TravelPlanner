"""
Common API models
"""

from typing import Any

from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    """
    Unified API response envelope
    """

    code: int = Field(default=0, description="0 means success; non-zero means error")
    msg: str = Field(default="ok", description="Human-readable message")
    data: Any | None = Field(default=None, description="Payload data")

    class Config:
        json_schema_extra = {"example": {"code": 0, "msg": "ok", "data": {"items": []}}}
