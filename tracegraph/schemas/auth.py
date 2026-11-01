from pydantic import BaseModel, ConfigDict, Field


class AuthContext(BaseModel):
    """
    #Feature: Authorization
    #Scenario: Resolved security context attached to request.state.auth
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(min_length=1)
    role_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
