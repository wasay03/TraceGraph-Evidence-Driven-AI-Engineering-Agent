from dataclasses import dataclass, field

from tracegraph.extract.builder import GraphBuilder
from tracegraph.extract.index import ProgramIndex
from tracegraph.extract.resolver import FunctionScope, NameResolver, TypeInference


@dataclass(slots=True)
class AnalysisContext:
    """
    #Feature: Extraction pipeline
    #Scenario: Shared state handed to every pass after structure: builder, index, resolvers, cached scopes.
               orm_tables maps class qname -> table name; orm_columns maps (class qname, attr) -> column name.
    #Complexity: Time O(1) - constant
    """

    builder: GraphBuilder
    index: ProgramIndex
    resolver: NameResolver
    types: TypeInference
    scopes: dict[str, FunctionScope] = field(default_factory=dict)
    orm_tables: dict[str, str] = field(default_factory=dict)
    orm_columns: dict[tuple[str, str], str] = field(default_factory=dict)

    @classmethod
    def create(cls, builder: GraphBuilder, index: ProgramIndex) -> "AnalysisContext":
        """
        #Feature: Extraction pipeline
        #Scenario: Build resolvers over an index filled by the structure pass
        #Complexity: Time O(1) - constant
        """
        resolver = NameResolver(index)
        return cls(builder, index, resolver, TypeInference(resolver))

    def scope(self, qname: str) -> FunctionScope:
        """
        #Feature: Extraction pipeline
        #Scenario: Lazily computed, cached type scope of one function
        #Complexity: Time O(n) first call, then O(1)

        Raises:
            KeyError: When qname is not an indexed function.
        """
        if qname not in self.scopes:
            self.scopes[qname] = self.types.scope(self.index.functions[qname])
        return self.scopes[qname]
