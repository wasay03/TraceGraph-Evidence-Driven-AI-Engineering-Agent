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


def dotted_name(expr: ast.expr) -> str | None:
    """
    #Feature: AST helpers
    #Scenario: "a.b.c" for Name/Attribute chains
    #Complexity: Time O(d) - chain depth
    """
    parts = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    return ".".join([expr.id, *reversed(parts)]) if isinstance(expr, ast.Name) else None


def guarded_names(fn: ast.AST) -> set[str]:
    """
    #Feature: Facts pass
    #Scenario: Dotted expressions None-checked or truth-tested anywhere in the function (flow-insensitive)
    #Complexity: Time O(n) - linear in function nodes
    """
    guarded: set[str] = set()
    tests = [n.test for n in ast.walk(fn) if isinstance(n, (ast.If, ast.While, ast.IfExp, ast.Assert))]
    tests += [v for n in ast.walk(fn) if isinstance(n, ast.BoolOp) for v in n.values]
    for test in tests:
        for node in ast.walk(test):
            if isinstance(node, ast.Compare) and any(isinstance(c, ast.Constant) and c.value is None
                                                     for c in node.comparators):
                guarded.add(dotted_name(node.left) or "")
            elif isinstance(node, (ast.Name, ast.Attribute)) and node is test:
                guarded.add(dotted_name(node) or "")
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                guarded.add(dotted_name(node.operand) or "")
            elif call_name(node) == "isinstance" and node.args:
                guarded.add(dotted_name(node.args[0]) or "")
    return guarded - {""}
