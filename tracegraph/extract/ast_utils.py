import ast


def const_str(expr: ast.expr | None) -> str | None:
    """
    #Feature: AST helpers
    #Scenario: Value of a string literal, else None
    #Complexity: Time O(1) - constant
    """
    return expr.value if isinstance(expr, ast.Constant) and isinstance(expr.value, str) else None


def keyword(call: ast.Call, name: str) -> ast.expr | None:
    """
    #Feature: AST helpers
    #Scenario: Value of a keyword argument of a call, else None
    #Complexity: Time O(k) - linear in keywords
    """
    return next((k.value for k in call.keywords if k.arg == name), None)


def call_name(call: ast.AST) -> str | None:
    """
    #Feature: AST helpers
    #Scenario: Last segment of the callee name: Depends, mapped_column, select, ...
    #Complexity: Time O(d) - linear in callee depth
    """
    if not isinstance(call, ast.Call):
        return None
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else None


def literal_bool(expr: ast.expr | None) -> bool | None:
    """
    #Feature: AST helpers
    #Scenario: True/False literal value, else None
    #Complexity: Time O(1) - constant
    """
    return expr.value if isinstance(expr, ast.Constant) and isinstance(expr.value, bool) else None


def body_nodes(fn: ast.AST) -> list[ast.AST]:
    """
    #Feature: AST helpers
    #Scenario: Nodes of a function body excluding nested function and class definitions
    #Complexity: Time O(n) - linear in body nodes
    """
    out, stack = [], list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        out.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return out


def dotted_root(expr: ast.expr) -> str | None:
    """
    #Feature: AST helpers
    #Scenario: Root name of an attribute chain (op in op.add_column)
    #Complexity: Time O(d) - chain depth
    """
    while isinstance(expr, ast.Attribute):
        expr = expr.value
    return expr.id if isinstance(expr, ast.Name) else None
