from pydantic import BaseModel


class HealthResponse(BaseModel):
    """
    #Feature: Health
    #Scenario: Liveness and database readiness report
    #Complexity: Time O(1) - constant
    """

    status: str
    database: str
    server_version: str | None = None
