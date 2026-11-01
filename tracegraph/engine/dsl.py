import re
from dataclasses import dataclass, field
from typing import Any

from tracegraph.constants.engine import DEFAULT_MAX_HOPS
from tracegraph.errors import Errors

_TOKEN = re.compile(r'''\s*(?:\#[^\n]*\n?\s*)*(?:
    (?P<string>"(?:[^"\\]|\\.)*") | (?P<number>-?\d+(?:\.\d+)?) | (?P<prop>[A-Z_]\w*\.\w+) | (?P<name>[A-Za-z_]\w*) |
    (?P<punct>:-|\?-|==|!=|[(),.=])
)''', re.VERBOSE)
_LITERALS = {"true": True, "false": False, "null": None}
_AGGREGATES = frozenset({"count", "count_distinct", "min", "max", "sum", "argmax"})


@dataclass(frozen=True, slots=True)
class Var:
    """
    #Feature: Textual DSL (PRD 7.4)
    #Scenario: Logic variable, bound to a node id during evaluation
    #Complexity: Time O(1) - constant
    """

    name: str


@dataclass(frozen=True, slots=True)
class Atom:
    """
    #Feature: Textual DSL
    #Scenario: Node type, edge label or derived predicate applied to variables
    #Complexity: Time O(1) - constant
    """

    pred: str
    args: tuple[Var, ...]


@dataclass(frozen=True, slots=True)
class ReachAtom:
    """
    #Feature: Textual DSL
    #Scenario: reach(Src, Dst, "rpq", max_hops=n); Src must be bound by another literal
    #Complexity: Time O(1) - constant
    """

    src: Var
    dst: Var
    rpq: str
    max_hops: int = DEFAULT_MAX_HOPS


@dataclass(frozen=True, slots=True)
class Equals:
    """
    #Feature: Textual DSL
    #Scenario: Var == type("natural key"); binds or tests the variable against one node
    #Complexity: Time O(1) - constant
    """

    var: Var
    type: str
    key: str


@dataclass(frozen=True, slots=True)
class PropTest:
    """
    #Feature: Textual DSL
    #Scenario: Var.prop == literal or Var.prop != literal, on a bound variable
    #Complexity: Time O(1) - constant
    """

    var: Var
    prop: str
    value: Any
    negate: bool = False


@dataclass(frozen=True, slots=True)
class Negated:
    """
    #Feature: Textual DSL
    #Scenario: not pred(...) scope Type: three-valued negation over the named scope (PRD 7.5)
    #Complexity: Time O(1) - constant
    """

    atom: Atom
    scope: str


Literal = Atom | ReachAtom | Equals | PropTest | Negated


@dataclass(frozen=True, slots=True)
class Rule:
    """
    #Feature: Textual DSL
    #Scenario: head(...) :- body.
    #Complexity: Time O(1) - constant
    """

    head: Atom
    body: tuple[Literal, ...]


@dataclass(frozen=True, slots=True)
class AggregateSpec:
    """
    #Feature: Textual DSL
    #Scenario: aggregate(Group, fn(Var or Var.prop)); Group is optional
    #Complexity: Time O(1) - constant
    """

    group: Var | None
    fn: str
    var: Var
    prop: str | None = None


@dataclass(frozen=True, slots=True)
class QueryClause:
    """
    #Feature: Textual DSL
    #Scenario: ?- body. optionally aggregated, ordered by output column and limited
    #Complexity: Time O(1) - constant
    """

    body: tuple[Literal, ...]
    aggregate: AggregateSpec | None = None
    order_by: int | None = None
    descending: bool = False
    limit: int | None = None


@dataclass(slots=True)
class Program:
    """
    #Feature: Textual DSL
    #Scenario: Parsed rules and queries of one DSL text
    #Complexity: Time O(1) - constant
    """

    rules: list[Rule] = field(default_factory=list)
    queries: list[QueryClause] = field(default_factory=list)


def _tokenize(text: str) -> list[tuple[str, str]]:
    """
    #Feature: Textual DSL
    #Scenario: Tokens as (kind, text); comments start with #
    #Complexity: Time O(n) - text length

    Raises:
        Errors.Domain.QueryType: On a character that starts no token.
    """
    tokens, pos = [], 0
    stripped = re.sub(r"#[^\n]*", "", text).rstrip()
    while pos < len(stripped):
        match = _TOKEN.match(stripped, pos)
        if match is None:
            raise Errors.Domain.QueryType(f"DSL syntax error near {stripped[pos:pos + 30]!r}.", {"position": pos})
        tokens.append((match.lastgroup, match.group(match.lastgroup)))
        pos = match.end()
    return tokens


class _Parser:
    """
    #Feature: Textual DSL
    #Scenario: Recursive-descent parser over the token list
    #Complexity: Time O(t) - tokens
    """

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        """
        #Feature: Textual DSL
        #Scenario: Start at the first token
        #Complexity: Time O(1) - constant
        """
        self.tokens, self.pos = tokens, 0

    def _peek(self) -> str | None:
        """
        #Feature: Textual DSL
        #Scenario: Text of the next token, or None at the end
        #Complexity: Time O(1) - constant
        """
        return self.tokens[self.pos][1] if self.pos < len(self.tokens) else None

    def _next(self, kind: str | None = None) -> str:
        """
        #Feature: Textual DSL
        #Scenario: Consume one token, optionally of a required kind
        #Complexity: Time O(1) - constant

        Raises:
            Errors.Domain.QueryType: At the end of input or on the wrong kind.
        """
        if self.pos >= len(self.tokens):
            raise Errors.Domain.QueryType("DSL text ended early; every clause ends with a full stop.", {})
        token_kind, text = self.tokens[self.pos]
        if kind is not None and token_kind != kind:
            raise Errors.Domain.QueryType(f"Expected a {kind} in the DSL, got {text!r}.", {"token": text})
        self.pos += 1
        return text

    def _accept(self, text: str) -> bool:
        """
        #Feature: Textual DSL
        #Scenario: Consume the next token only when it is exactly this text
        #Complexity: Time O(1) - constant
        """
        if self._peek() == text:
            self.pos += 1
            return True
        return False

    def _expect(self, text: str) -> None:
        """
        #Feature: Textual DSL
        #Scenario: Consume exactly this token
        #Complexity: Time O(1) - constant

        Raises:
            Errors.Domain.QueryType: On anything else.
        """
        if not self._accept(text):
            raise Errors.Domain.QueryType(f"Expected {text!r} in the DSL, got {self._peek()!r}.", {"expected": text})

    def _var(self) -> Var:
        """
        #Feature: Textual DSL
        #Scenario: Variables start with an upper-case letter or underscore
        #Complexity: Time O(1) - constant

        Raises:
            Errors.Domain.QueryType: On a lower-case name.
        """
        name = self._next("name")
        if not (name[0].isupper() or name[0] == "_"):
            raise Errors.Domain.QueryType(f"Expected a variable (upper-case), got {name!r}.", {"token": name})
        return Var(name)

    def _value(self) -> Any:
        """
        #Feature: Textual DSL
        #Scenario: String, number, true, false or null
        #Complexity: Time O(1) - constant

        Raises:
            Errors.Domain.QueryType: On anything else.
        """
        kind, text = self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)
        self.pos += 1
        if kind == "string":
            return text[1:-1].replace('\\"', '"')
        if kind == "number":
            return float(text) if "." in text else int(text)
        if text in _LITERALS:
            return _LITERALS[text]
        raise Errors.Domain.QueryType(f"Expected a literal value in the DSL, got {text!r}.", {"token": text})

    def _atom(self) -> Atom:
        """
        #Feature: Textual DSL
        #Scenario: name(Var, ...)
        #Complexity: Time O(a) - arguments
        """
        name = self._next("name")
        self._expect("(")
        args = [self._var()]
        while self._accept(","):
            args.append(self._var())
        self._expect(")")
        return Atom(name, tuple(args))

    def _reach(self) -> ReachAtom:
        """
        #Feature: Textual DSL
        #Scenario: reach(Src, Dst, "rpq"[, max_hops=n])
        #Complexity: Time O(1) - constant
        """
        self._next()
        self._expect("(")
        src, _, dst, _, rpq = self._var(), self._expect(","), self._var(), self._expect(","), self._value()
        hops = DEFAULT_MAX_HOPS
        if self._accept(","):
            self._expect("max_hops")
            self._expect("=")
            hops = self._value()
        self._expect(")")
        return ReachAtom(src, dst, rpq, hops)

    def _prop_test(self) -> PropTest:
        """
        #Feature: Textual DSL
        #Scenario: Var.prop == literal or Var.prop != literal
        #Complexity: Time O(1) - constant
        """
        var, prop = self._next("prop").split(".", 1)
        negate = self._peek() == "!="
        self.pos += 1
        return PropTest(Var(var), prop, self._value(), negate)

    def _literal(self) -> Literal:
        """
        #Feature: Textual DSL
        #Scenario: One body literal
        #Complexity: Time O(a) - arguments
        """
        if self.tokens[self.pos][0] == "prop":
            return self._prop_test()
        if self._accept("not"):
            atom = self._atom()
            self._expect("scope")
            return Negated(atom, self._next("name"))
        if self._peek() == "reach":
            return self._reach()
        if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1][1] == "==":
            var = self._var()
            self._expect("==")
            type_name = self._next("name")
            self._expect("(")
            key = self._value()
            self._expect(")")
            return Equals(var, type_name, key)
        return self._atom()

    def _body(self) -> tuple[Literal, ...]:
        """
        #Feature: Textual DSL
        #Scenario: Comma-separated literals
        #Complexity: Time O(l) - literals
        """
        body = [self._literal()]
        while self._accept(","):
            body.append(self._literal())
        return tuple(body)

    def _aggregate(self) -> AggregateSpec:
        """
        #Feature: Textual DSL
        #Scenario: aggregate(Group, fn(Var)) or aggregate(fn(Var.prop))
        #Complexity: Time O(1) - constant

        Raises:
            Errors.Domain.QueryType: On an unknown aggregate function.
        """
        self._next()
        self._expect("(")
        group = None
        if self.tokens[self.pos][1][0].isupper():
            group = self._var()
            self._expect(",")
        fn = self._next("name")
        if fn not in _AGGREGATES:
            raise Errors.Domain.QueryType(f"Unknown aggregate {fn!r}; use one of {sorted(_AGGREGATES)}.", {"fn": fn})
        self._expect("(")
        kind, text = self.tokens[self.pos]
        self.pos += 1
        var, _, prop = text.partition(".") if kind == "prop" else (text, "", "")
        self._expect(")")
        self._expect(")")
        return AggregateSpec(group, fn, Var(var), prop or None)

    def _query(self) -> QueryClause:
        """
        #Feature: Textual DSL
        #Scenario: ?- body [order by n [asc|desc]] [limit n].
        #Complexity: Time O(l) - literals
        """
        aggregate = None
        if self._peek() == "aggregate":
            aggregate = self._aggregate()
            self._expect(":-")
        body, order_by, descending, limit = self._body(), None, False, None
        if self._accept("order"):
            self._expect("by")
            order_by = self._value()
            descending = self._accept("desc") or (self._accept("asc") and False)
        if self._accept("limit"):
            limit = self._value()
        return QueryClause(body, aggregate, order_by, descending, limit)

    def program(self) -> Program:
        """
        #Feature: Textual DSL
        #Scenario: Clauses until the end of the text
        #Complexity: Time O(t) - tokens
        """
        program = Program()
        while self.pos < len(self.tokens):
            if self._accept("?-"):
                program.queries.append(self._query())
            else:
                head = self._atom()
                self._expect(":-")
                program.rules.append(Rule(head, self._body()))
            self._expect(".")
        return program


def parse_program(text: str) -> Program:
    """
    #Feature: Textual DSL (PRD 7.4)
    #Scenario: Parse rules and queries; syntax errors are query errors the caller can show
    #Complexity: Time O(n) - text length

    Raises:
        ValueError: When text is None.
        Errors.Domain.QueryType: On a syntax error.
    """
    if text is None:
        raise ValueError("[parse_program] 'text' is required.")
    try:
        return _Parser(_tokenize(text)).program()
    except IndexError as exc:
        raise Errors.Domain.QueryType("DSL text ended early; every clause ends with a full stop.", {}) from exc
