from typing import Any


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """
    #Feature: LLM utility
    #Scenario: Resolve local "$ref": "#/$defs/X" references and drop $defs, for providers that want flat schemas
    #Complexity: Time O(s) - schema size (definitions are not recursive in tool schemas)

    Args:
        schema: JSON Schema produced by Pydantic.

    Returns:
        Equivalent schema without $ref/$defs.

    Raises:
        ValueError: When schema is None or a reference cannot be resolved.
    """
    if schema is None:
        raise ValueError("[inline_refs] 'schema' is required.")
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(v) for v in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            if name not in defs:
                raise ValueError(f"[inline_refs] Unresolvable reference {node['$ref']!r}.")
            return walk({**defs[name], **{k: v for k, v in node.items() if k != "$ref"}})
        return {k: walk(v) for k, v in node.items() if k != "$defs"}

    return walk(schema)
