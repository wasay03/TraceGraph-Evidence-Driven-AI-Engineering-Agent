from pydantic import BaseModel, field_validator


class OrderIn(BaseModel):
    tenant_id: int
    total: int
    discount_code: str | None = None

    @field_validator("total")
    @classmethod
    def total_positive(cls, value: int) -> int:
        if value < 0:
            raise ValueError("total must be positive")
        return value


class OrderOut(BaseModel):
    id: int
    status: str
    total: int
