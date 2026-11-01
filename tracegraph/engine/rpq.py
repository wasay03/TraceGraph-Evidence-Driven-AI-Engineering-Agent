import re
from dataclasses import dataclass, field
from functools import lru_cache

from tracegraph.constants.engine import RPQ_INVERSE_SUFFIXES
from tracegraph.errors import Errors
from tracegraph.ontology import Registry

_TOKEN = re.compile(r"\s*(\(|\)|\||\*|\+|\?|\.|·|[A-Za-z_][A-Za-z0-9_]*(?:\^-1|~)?)")

Label = tuple[str, str]  # (edge type name, "fwd" | "rev")


@dataclass(slots=True)
class Nfa:
    """
    #Feature: Regular path queries
    #Scenario: Thompson NFA over typed edge labels; transitions[state] = [(label or None for epsilon, next)]
    #Complexity: Time O(1) - constant
    """

    start: int
    accept: int
    transitions: dict[int, list[tuple[Label | None, int]]] = field(default_factory=dict)

    def closure(self, states: frozenset[int]) -> frozenset[int]:
        """
        #Feature: Regular path queries
        #Scenario: Epsilon closure of a state set
        #Complexity: Time O(q) - linear in states
        """
        stack, seen = list(states), set(states)
        while stack:
            for label, nxt in self.transitions.get(stack.pop(), []):
                if label is None and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return frozenset(seen)

    def labels_from(self, states: frozenset[int]) -> dict[Label, frozenset[int]]:
        """
        #Feature: Regular path queries
        #Scenario: For a closed state set, the labelled moves available and their closed target sets
        #Complexity: Time O(q) - linear in transitions out of states
        """
        moves: dict[Label, set[int]] = {}
        for state in states:
            for label, nxt in self.transitions.get(state, []):
                if label is not None:
                    moves.setdefault(label, set()).add(nxt)
        return {label: self.closure(frozenset(targets)) for label, targets in moves.items()}

    @property
    def labels(self) -> set[Label]:
        """
        #Feature: Regular path queries
        #Scenario: All edge labels the automaton can consume
        #Complexity: Time O(t) - linear in transitions
        """
        return {label for moves in self.transitions.values() for label, _ in moves if label is not None}


class _Parser:
    """
    #Feature: Regular path queries
    #Scenario: Recursive-descent parser building the NFA directly (alternation, concatenation, * + ?)
    #Complexity: Time O(t) - linear in tokens
    """

    def __init__(self, text: str, registry: Registry) -> None:
        """
        #Feature: Regular path queries
        #Scenario: Tokenise the expression
        #Complexity: Time O(t) - linear in text

        Raises:
            Errors.Domain.QueryType: On characters that are not part of the grammar.
        """
        self.registry = registry
        self.tokens, pos = [], 0
        for match in _TOKEN.finditer(text):
            if match.start() != pos:
                break
            self.tokens.append(match.group(1))
            pos = match.end()
        if text[pos:].strip():
            raise Errors.Domain.QueryType(f"Invalid RPQ near {text[pos:pos + 20]!r}.", {"rpq": text})
        self.i = 0
        self.nfa = Nfa(0, 0)
        self.count = 0

    def _state(self) -> int:
        """
        #Feature: Regular path queries
        #Scenario: Allocate a fresh state
        #Complexity: Time O(1) - constant
        """
        self.count += 1
        return self.count

    def _link(self, a: int, label: Label | None, b: int) -> None:
        """
        #Feature: Regular path queries
        #Scenario: Add a transition
        #Complexity: Time O(1) - constant
        """
        self.nfa.transitions.setdefault(a, []).append((label, b))

    def _peek(self) -> str | None:
        """
        #Feature: Regular path queries
        #Scenario: Next token without consuming it
        #Complexity: Time O(1) - constant
        """
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def _label(self, token: str) -> Label:
        """
        #Feature: Regular path queries
        #Scenario: Resolve an edge name, an inverse name or NAME^-1 / NAME~ to (edge type, direction)
        #Complexity: Time O(e) - linear in edge types for inverse lookup

        Raises:
            Errors.Domain.QueryType: When the label is not a registered edge or inverse name.
        """
        flip = token.endswith(RPQ_INVERSE_SUFFIXES)
        name = token.removesuffix("^-1").removesuffix("~")
        if self.registry.has_edge_type(name):
            return (name, "rev" if flip else "fwd")
        inverse = next((e.name for e in self.registry.edge_types if e.inverse == name), None)
        if inverse is None:
            raise Errors.Domain.QueryType(f"Unknown edge label {name!r} in RPQ.", {"label": name})
        return (inverse, "fwd" if flip else "rev")

    def _atom(self) -> tuple[int, int]:
        """
        #Feature: Regular path queries
        #Scenario: Label or parenthesised sub-expression
        #Complexity: Time O(t) - tokens consumed

        Raises:
            Errors.Domain.QueryType: On unbalanced parentheses or a missing operand.
        """
        token = self._peek()
        if token == "(":
            self.i += 1
            fragment = self._alternation()
            if self._peek() != ")":
                raise Errors.Domain.QueryType("Unbalanced parentheses in RPQ.", {})
            self.i += 1
            return fragment
        if token is None or token in ")|*+?.·":
            raise Errors.Domain.QueryType(f"Expected an edge label in RPQ, got {token!r}.", {})
        self.i += 1
        a, b = self._state(), self._state()
        self._link(a, self._label(token), b)
        return a, b

    def _repeat(self) -> tuple[int, int]:
        """
        #Feature: Regular path queries
        #Scenario: Postfix * (zero or more), + (one or more), ? (optional)
        #Complexity: Time O(t) - tokens consumed
        """
        start, end = self._atom()
        while self._peek() in ("*", "+", "?"):
            op = self.tokens[self.i]
            self.i += 1
            a, b = self._state(), self._state()
            self._link(a, None, start)
            self._link(end, None, b)
            if op in ("*", "?"):
                self._link(a, None, b)
            if op in ("*", "+"):
                self._link(end, None, start)
            start, end = a, b
        return start, end

    def _concatenation(self) -> tuple[int, int]:
        """
        #Feature: Regular path queries
        #Scenario: Sequence separated by '.', '·' or juxtaposition
        #Complexity: Time O(t) - tokens consumed
        """
        start, end = self._repeat()
        while self._peek() not in (None, ")", "|"):
            if self._peek() in (".", "·"):
                self.i += 1
            nxt_start, nxt_end = self._repeat()
            self._link(end, None, nxt_start)
            end = nxt_end
        return start, end

    def _alternation(self) -> tuple[int, int]:
        """
        #Feature: Regular path queries
        #Scenario: Alternatives separated by '|'
        #Complexity: Time O(t) - tokens consumed
        """
        branches = [self._concatenation()]
        while self._peek() == "|":
            self.i += 1
            branches.append(self._concatenation())
        if len(branches) == 1:
            return branches[0]
        a, b = self._state(), self._state()
        for start, end in branches:
            self._link(a, None, start)
            self._link(end, None, b)
        return a, b

    def parse(self) -> Nfa:
        """
        #Feature: Regular path queries
        #Scenario: Parse the whole expression into an NFA
        #Complexity: Time O(t) - linear in tokens

        Raises:
            Errors.Domain.QueryType: On trailing tokens or an empty expression.
        """
        if not self.tokens:
            raise Errors.Domain.QueryType("Empty RPQ.", {})
        start, end = self._alternation()
        if self._peek() is not None:
            raise Errors.Domain.QueryType(f"Unexpected {self._peek()!r} in RPQ.", {})
        self.nfa.start, self.nfa.accept = start, end
        return self.nfa


@lru_cache(maxsize=512)
def _compile_cached(text: str, registry_id: int, registry: Registry) -> Nfa:
    """
    #Feature: Regular path queries
    #Scenario: Cache compiled automata per (expression, registry)
    #Complexity: Time O(t) first call, then O(1)
    """
    return _Parser(text, registry).parse()


def compile_rpq(text: str, registry: Registry) -> Nfa:
    """
    #Feature: Regular path queries
    #Scenario: Compile and type-check an RPQ against the registry
    #Complexity: Time O(t) - linear in tokens (cached)

    Raises:
        ValueError: When text or registry is missing.
        Errors.Domain.QueryType: When the expression is malformed or uses unknown labels.
    """
    if not text or registry is None:
        raise ValueError("[compile_rpq] 'text' and 'registry' are required.")
    return _compile_cached(text, id(registry), registry)
