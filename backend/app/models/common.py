"""
Common API models
"""
from pydantic import BaseModel, Field
from typing import Any, Optional


class APIResponse(BaseModel):
	"""
	Unified API response envelope
	"""
	code: int = Field(default=0, description="0 means success; non-zero means error")
	msg: str = Field(default="ok", description="Human-readable message")
	data: Optional[Any] = Field(default=None, description="Payload data")

	class Config:
		json_schema_extra = {
			"example": {
				"code": 0,
				"msg": "ok",
				"data": {"items": []}
			}
		}



