from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class _Spec(BaseModel):
    """
    #Feature: ChangeSpec catalog (PRD 8.1, D11)
    #Scenario: Base for typed perturbations; targets are natural keys (resolved, never guessed)
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class MakeColumnNullable(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: Column becomes nullable, e.g. column="orders.status"
    #Complexity: Time O(1) - constant
    """

    kind: Literal["make_column_nullable"] = "make_column_nullable"
    column: str = Field(min_length=3, pattern=r"^[\w]+\.[\w]+$")


class DropColumn(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: Column is removed
    #Complexity: Time O(1) - constant
    """

    kind: Literal["drop_column"] = "drop_column"
    column: str = Field(min_length=3, pattern=r"^[\w]+\.[\w]+$")


class AddEnumMember(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: New member on an Enum class, e.g. enum="app.models.OrderStatus", member="CANCELLED"
    #Complexity: Time O(1) - constant
    """

    kind: Literal["add_enum_member"] = "add_enum_member"
    enum: str = Field(min_length=1)
    member: str = Field(min_length=1, pattern=r"^[A-Za-z_]\w*$")
    value: str | None = None


class ChangeReturnType(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: Function return annotation changes, e.g. new_type="int | None"
    #Complexity: Time O(1) - constant
    """

    kind: Literal["change_return_type"] = "change_return_type"
    function: str = Field(min_length=1)
    new_type: str = Field(min_length=1)


class ParamChange(BaseModel):
    """
    #Feature: ChangeSpec catalog
    #Scenario: Parameter added by ChangeSignature
    #Complexity: Time O(1) - constant
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z_]\w*$")
    has_default: bool = False
    keyword_only: bool = False


class ChangeSignature(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: Add, remove or rename parameters of a function
    #Complexity: Time O(1) - constant
    """

    kind: Literal["change_signature"] = "change_signature"
    function: str = Field(min_length=1)
    add: list[ParamChange] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)
    rename: dict[str, str] = Field(default_factory=dict)


class RemoveSymbol(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: A function, method or class is deleted
    #Complexity: Time O(1) - constant
    """

    kind: Literal["remove_symbol"] = "remove_symbol"
    symbol: str = Field(min_length=1)


class ModifyBody(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: Generic fallback: body changes, no BREAKS claims
    #Complexity: Time O(1) - constant
    """

    kind: Literal["modify_body"] = "modify_body"
    function: str = Field(min_length=1)


class RenameSymbol(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: A function, method or class gets a new name
    #Complexity: Time O(1) - constant
    """

    kind: Literal["rename_symbol"] = "rename_symbol"
    symbol: str = Field(min_length=1)
    new_name: str = Field(pattern=r"^[A-Za-z_]\w*$")


class AddColumn(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: New column on a table, e.g. table="public.orders"
    #Complexity: Time O(1) - constant
    """

    kind: Literal["add_column"] = "add_column"
    table: str = Field(min_length=1)
    name: str = Field(pattern=r"^[A-Za-z_]\w*$")
    sql_type: str = Field(min_length=1)
    nullable: bool = True
    default: str | None = None


class ChangeColumnType(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: Column changes its SQL type
    #Complexity: Time O(1) - constant
    """

    kind: Literal["change_column_type"] = "change_column_type"
    column: str = Field(min_length=3, pattern=r"^[\w]+\.[\w]+$")
    new_type: str = Field(min_length=1)


class AddRaise(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: A function starts raising an exception (class key or builtin name)
    #Complexity: Time O(1) - constant
    """

    kind: Literal["add_raise"] = "add_raise"
    function: str = Field(min_length=1)
    exception: str = Field(min_length=1)


class ChangeEndpointContract(_Spec):
    """
    #Feature: ChangeSpec catalog
    #Scenario: Endpoint request or response schema changes, e.g. endpoint="POST /orders"
    #Complexity: Time O(1) - constant
    """

    kind: Literal["change_endpoint_contract"] = "change_endpoint_contract"
    endpoint: str = Field(min_length=1)
    new_request: str | None = None
    new_response: str | None = None


ChangeSpec = Annotated[
    Union[MakeColumnNullable, DropColumn, AddEnumMember, ChangeReturnType, ChangeSignature, RemoveSymbol, ModifyBody,
          RenameSymbol, AddColumn, ChangeColumnType, AddRaise, ChangeEndpointContract],
    Field(discriminator="kind"),
]
