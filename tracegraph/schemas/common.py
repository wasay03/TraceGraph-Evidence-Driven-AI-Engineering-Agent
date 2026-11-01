from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """
    #Feature: Pagination
    #Scenario: Uniform paged list envelope
    #Complexity: Time O(1) - constant
    """

    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    limit: int = Field(ge=1)
