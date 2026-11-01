from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RepoCreateRequest(BaseModel):
    """
    #Feature: Repositories API
    #Scenario: Register a local git repository or directory (file:// URL or absolute path)
    #Complexity: Time O(1) - constant
    """

    url: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    default_branch: str = Field(default="main", min_length=1, max_length=200)


class RepoResponse(BaseModel):
    """
    #Feature: Repositories API
    #Scenario: Registered repository
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    name: str
    default_branch: str
    created_at: datetime
