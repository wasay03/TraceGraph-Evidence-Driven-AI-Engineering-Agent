class OntologyPermissions:
    """
    #Feature: Authorization
    #Scenario: Permissions for the ontology registry
    #Complexity: Time O(1) - constant
    """

    read = "ontology.read"
    manage = "ontology.manage"


class RepoPermissions:
    """
    #Feature: Authorization
    #Scenario: Permissions for repositories and snapshots
    #Complexity: Time O(1) - constant
    """

    create = "repo.create"
    read = "repo.read"
    execute = "repo.execute"


class QueryPermissions:
    """
    #Feature: Authorization
    #Scenario: Permissions for the reasoning engine and impact analysis
    #Complexity: Time O(1) - constant
    """

    execute = "query.execute"
    read = "query.read"


class SystemPermissions:
    """
    #Feature: Authorization
    #Scenario: Permissions for operational endpoints
    #Complexity: Time O(1) - constant
    """

    read = "system.read"


ontology = OntologyPermissions()
repo = RepoPermissions()
query = QueryPermissions()
system = SystemPermissions()

ALL_PERMISSIONS: frozenset[str] = frozenset(
    {
        ontology.read,
        ontology.manage,
        repo.create,
        repo.read,
        repo.execute,
        query.execute,
        query.read,
        system.read,
    }
)
